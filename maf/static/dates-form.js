// The profile form: Dates replies are encrypted for your device, so a profile is only posted from a browser
// that can encrypt. The server refuses one without this mark (post.py, save_profile).
(function () {
  const mark = document.querySelector("input[name='can_encrypt']");
  if (mark && window.crypto?.subtle && window.indexedDB) mark.value = "1";
})();
