# Setting up MAF on AWS

You run these yourself, once. Every command uses `--profile rilley --region us-east-1`: the server lives in
us-east-1 (N. Virginia). Email (SES) lives in us-west-2 (Oregon), where the domain is verified and production
access was requested, so the SES ARNs below say us-west-2 and the server's `AWS_REGION` is us-west-2.
Replace the two placeholders first:

- `ACCOUNT_ID`: your 12-digit AWS account id.
- `MY_IP`: your public IP, for SSH (for example `203.0.113.7`).

Paste the commands in one terminal (bash or zsh) so the shell variables carry over.

```sh
export ACCOUNT_ID=123456789012
export MY_IP=203.0.113.7
```

## 1. Security group

Opens 443 and 80 to the world (80 is only for the HTTPS certificate and redirect) and 22 to you.

```sh
VPC_ID=$(aws --profile rilley --region us-east-1 ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)

SG_ID=$(aws --profile rilley --region us-east-1 ec2 create-security-group --group-name maf --description "MAF web server" \
  --vpc-id "$VPC_ID" --query GroupId --output text)

aws --profile rilley --region us-east-1 ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 443 --cidr 0.0.0.0/0
aws --profile rilley --region us-east-1 ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 80 --cidr 0.0.0.0/0
aws --profile rilley --region us-east-1 ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr "$MY_IP/32"
```

## 2. IAM role for sending email

The server may only send mail from the `maforum.net` identity. No access keys exist anywhere.

```sh
cat > trust.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "ec2.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
EOF

cat > ses-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["ses:SendEmail", "ses:SendRawEmail"],
    "Resource": "arn:aws:ses:us-west-2:${ACCOUNT_ID}:identity/maforum.net"
  }]
}
EOF

aws --profile rilley --region us-east-1 iam create-role --role-name maf-server --assume-role-policy-document file://trust.json
aws --profile rilley --region us-east-1 iam put-role-policy --role-name maf-server --policy-name send-ses-email --policy-document file://ses-policy.json
aws --profile rilley --region us-east-1 iam create-instance-profile --instance-profile-name maf-server
aws --profile rilley --region us-east-1 iam add-role-to-instance-profile --instance-profile-name maf-server --role-name maf-server
```

While SES is still in sandbox mode, SES also checks the recipient. To test before production access
is granted, add each verified recipient's ARN (`arn:aws:ses:us-west-2:ACCOUNT_ID:identity/you@example.com`)
to `Resource` for now. Once production access is approved, the policy above is enough.

## 3. SSH key pair

```sh
aws --profile rilley --region us-east-1 ec2 create-key-pair --key-name maf --key-type ed25519 --query KeyMaterial --output text > ~/.ssh/maf.pem
chmod 400 ~/.ssh/maf.pem
```

## 4. The server

Looks up the current Ubuntu 24.04 arm64 image, then starts a `t4g.small` with an encrypted 20 GB disk.
The `Backup=maf-daily` tag is what the snapshot policy in step 6 looks for.

```sh
AMI_ID=$(aws --profile rilley --region us-east-1 ssm get-parameter \
  --name /aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id \
  --query Parameter.Value --output text)

sleep 15   # the new instance profile needs a few seconds before EC2 can use it

INSTANCE_ID=$(aws --profile rilley --region us-east-1 ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type t4g.small \
  --key-name maf \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile Name=maf-server \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=20,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=maf},{Key=Backup,Value=maf-daily}]' \
  --query 'Instances[0].InstanceId' --output text)

aws --profile rilley --region us-east-1 ec2 wait instance-running --instance-ids "$INSTANCE_ID"
```

## 5. Elastic IP (a fixed address)

```sh
ALLOC_ID=$(aws --profile rilley --region us-east-1 ec2 allocate-address --domain vpc --query AllocationId --output text)
aws --profile rilley --region us-east-1 ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID"
SERVER_IP=$(aws --profile rilley --region us-east-1 ec2 describe-addresses --allocation-ids "$ALLOC_ID" --query 'Addresses[0].PublicIp' --output text)
echo "$SERVER_IP"
```

## 6. Daily snapshots, kept 7 days

```sh
aws --profile rilley --region us-east-1 dlm create-default-role --resource-type snapshot   # fails harmlessly if the role already exists

cat > dlm-policy.json <<'EOF'
{
  "PolicyType": "EBS_SNAPSHOT_MANAGEMENT",
  "ResourceTypes": ["INSTANCE"],
  "TargetTags": [{ "Key": "Backup", "Value": "maf-daily" }],
  "Schedules": [{
    "Name": "daily",
    "CreateRule": { "Interval": 24, "IntervalUnit": "HOURS", "Times": ["03:00"] },
    "RetainRule": { "Count": 7 },
    "CopyTags": false
  }]
}
EOF

aws --profile rilley --region us-east-1 dlm create-lifecycle-policy \
  --description "MAF daily snapshot keep 7" \
  --state ENABLED \
  --execution-role-arn "arn:aws:iam::${ACCOUNT_ID}:role/AWSDataLifecycleManagerDefaultRole" \
  --policy-details file://dlm-policy.json
```

Snapshots hold the database, so treat them as private. They stay in your account.

## 7. DNS (Namecheap, Advanced DNS)

Add these two records (use the `SERVER_IP` printed in step 5):

| Type | Host | Value |
| --- | --- | --- |
| A Record | `@` | the Elastic IP |
| CNAME Record | `www` | `maforum.net.` |

The SES verification records (3 DKIM CNAMEs and the `_dmarc` TXT, see SPEC.md "Deploy") go in the same place.
Wait for the A record to resolve (`dig +short maforum.net`) before the first visit, so the certificate can be issued.

## 8. Install MAF on the server

From the repo folder on your machine:

```sh
scp -i ~/.ssh/maf.pem deploy/setup.sh ubuntu@"$SERVER_IP":
ssh -i ~/.ssh/maf.pem ubuntu@"$SERVER_IP" 'sudo bash setup.sh'
```

It takes a few minutes (the name-filter model is a big download). It creates the secrets and the signing
key on the server and never overwrites them if you run it again.

Then set your address for moderation emails:

```sh
ssh -i ~/.ssh/maf.pem ubuntu@"$SERVER_IP"
sudo nano /etc/maf/env        # replace CHANGE_ME_TO_THE_MAINTAINER_EMAIL
sudo systemctl restart maf
```

Open <https://maforum.net> to check it.

## Day to day

```sh
sudo bash /opt/maf/deploy/update.sh     # deploy the latest version from GitHub
sudo maf requests                       # the moderation CLI (also: hidden, show, unhide, nuke ...)
sudo systemctl status maf               # is it running?
sudo journalctl -u maf -n 50            # app output (it logs no requests or IPs)
```

Back up `/etc/maf/env` and `/var/lib/maf/signing.key` somewhere private. The snapshots cover them too,
but only while the disk exists.
