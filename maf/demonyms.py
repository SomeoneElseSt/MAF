"""Words for nationalities and peoples. The name check never treats these as a person's name
(the language model sometimes does, e.g. "Kazakh"). Singular forms only; plurals and "'s" are matched too.
Words that are also common first names or surnames are left out (Finn, Dane, Solomon, Sierra, Costa), and
multi-word ones are listed by their last word ("Costa Rican" -> rican)."""

DEMONYMS = frozenset("""
afghan albanian algerian american andorran angolan antiguan argentine argentinian armenian australian
austrian azerbaijani azeri bahamian bahraini bangladeshi barbadian belarusian belgian belizean beninese
bhutanese bolivian bosnian botswanan brazilian british briton bruneian bulgarian burkinabe burmese burundian
cambodian cameroonian canadian verdean chadian chilean chinese colombian comorian congolese
rican croatian cuban cypriot czech danish djiboutian dominican dutch ecuadorian egyptian
emirati english equatoguinean eritrean estonian eswatini ethiopian fijian filipino finnish french
gabonese gambian georgian german ghanaian greek grenadian guatemalan guinean guyanese haitian honduran
hungarian icelandic indian indonesian iranian iraqi irish israeli italian ivorian jamaican japanese
jordanian kazakh kazakhstani kenyan kiribati korean kosovar kuwaiti kyrgyz laotian lao latvian lebanese
liberian libyan liechtensteiner lithuanian luxembourgish malagasy malawian malaysian maldivian malian
maltese marshallese mauritanian mauritian mexican micronesian moldovan monegasque mongolian montenegrin
moroccan mozambican namibian nauruan nepali nepalese nicaraguan nigerian nigerien niuean norwegian omani
pakistani palauan palestinian panamanian papuan paraguayan peruvian polish pole portuguese qatari
romanian russian rwandan salvadoran samoan saudi scottish senegalese serbian seychellois
leonean singaporean slovak slovenian somali south african spanish spaniard sri lankan
sudanese surinamese swazi swedish swede swiss syrian taiwanese tajik tanzanian thai timorese togolese
tongan trinidadian tunisian turkish turk turkmen tuvaluan ugandan ukrainian uruguayan uzbek vanuatuan
venezuelan vietnamese welsh yemeni zambian zimbabwean
uyghur tatar kurd kurdish bashkir chechen dagestani buryat yakut circassian ossetian abkhaz pashtun
tamil punjabi bengali gujarati sindhi baloch hazara berber amazigh tuareg yoruba igbo hausa zulu xhosa
maasai amhara oromo tigrayan somalilander arab persian latino latina latinx hispanic slav slavic balkan
baltic nordic scandinavian caucasian asian african european eurasian
""".split())


def is_demonym(word: str) -> bool:
    """True for "kazakh", "kazakhs", "kazakh's" (lowercase words only)."""
    word = word.removesuffix("'s").removesuffix("’s")
    return word in DEMONYMS or word.removesuffix("s") in DEMONYMS or word.removesuffix("es") in DEMONYMS
