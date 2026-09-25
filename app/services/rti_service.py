"""RTI (Right to Information Act, 2005) applications: draft, generate, file, track.

Deadlines are *configuration*: ``RtiRules`` defaults are the Act's Section 7(1) periods
(30 days; 48 hours where the information concerns life or liberty) and are overridable
from settings. The clock is counted from the ``received_at`` date the applicant records
(receipt by the PIO); if unknown, the filing time is used and the UI says it is an estimate.

This module produces a *draft* in statutory language. It does not file anything with
any authority; ``FILED`` only records that the citizen has submitted it.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo

from app.core.authorization import AuthContext, Permission, require
from app.core.exceptions import NotConfigured, NotFound, ValidationFailed
from app.services.reference import generate_reference

# The application-wide clock (app.container.clock) is deliberately UTC, and every stored
# timestamp (created_at, due_at, audit logs) stays in UTC - that is correct and untouched here.
# This is only for the calendar day printed on the letter and baked into its reference number:
# without it, a citizen filing between roughly 00:00-05:29 IST would see YESTERDAY's date on
# their own letter, because that moment is still "yesterday" in UTC.
DISPLAY_TZ = ZoneInfo("Asia/Kolkata")

MAX_QUESTIONS = 20
MAX_QUESTION_LEN = 1000

# Statutory records worth demanding under RTI Section 2(j)/6(1), keyed by the same civic
# category taxonomy as complaint classification (app.services.classification_service.CATEGORIES).
# These are starting suggestions a citizen can pick from, edit, or ignore entirely - never
# submitted silently on their behalf.
RTI_CATEGORY_RECORDS: dict[str, tuple[str, ...]] = {
    "roads": (
        "Sanctioned Work Order / Tender copy for this stretch of road",
        "Technical sanction and detailed estimate",
        "Measurement Book (MB) entries recorded for this work",
        "Quality test / lab strength reports for the materials used",
        "Fund allocation versus actual utilisation ledger",
        "Name and contact of the engineer responsible for site inspection",
    ),
    "water": (
        "Sanctioned Work Order / Tender copy for this pipeline or supply line",
        "Maintenance and inspection log for this line",
        "Water quality test reports for this supply zone",
        "Fund allocation versus actual utilisation ledger",
        "Name and contact of the officer responsible for this ward",
    ),
    "electricity": (
        "Maintenance / inspection log for this transformer or line",
        "Complaint history and Action Taken Reports for this location",
        "Name and contact of the contractor or officer responsible for maintenance",
    ),
    "sanitation": (
        "Sanitation contract / tender covering this ward",
        "Collection schedule and compliance log for this area",
        "Name and contact of the officer responsible for this ward",
    ),
    "drainage": (
        "Sanctioned Work Order / Tender copy for this drain",
        "Desilting / maintenance schedule and log",
        "Fund allocation versus actual utilisation ledger",
    ),
    "encroachment": (
        "Survey / demarcation records for this site",
        "Notices issued and the enforcement action log",
        "Name and contact of the officer responsible for enforcement",
    ),
    "police": (
        "FIR / complaint register entry relating to this matter, if any",
        "Action Taken Report on file",
        "Name of the patrol / beat officer assigned to this area",
    ),
    "other": (
        "Relevant file notings and correspondence on this matter",
        "Name and contact of the officer responsible",
        "Action Taken Report on file, if any",
    ),
}


# Same records as RTI_CATEGORY_RECORDS above, in each supported language - same category keys, same
# order and count per category, so a checkbox means the same statutory record whichever language it
# is displayed in. Written and maintained here, never machine-translated at request time.
RTI_CATEGORY_RECORDS_I18N: dict[str, dict[str, tuple[str, ...]]] = {
    "hi": {
        "roads": ("इस सड़क खंड के लिए स्वीकृत कार्य आदेश / निविदा की प्रति", "तकनीकी स्वीकृति और विस्तृत प्राक्कलन", "इस कार्य हेतु दर्ज माप पुस्तिका (एमबी) प्रविष्टियां", "प्रयुक्त सामग्री की गुणवत्ता जांच / प्रयोगशाला शक्ति रिपोर्ट", "निधि आवंटन बनाम वास्तविक उपयोग का लेखा", "स्थल निरीक्षण के लिए जिम्मेदार अभियंता का नाम और संपर्क"),
        "water": ("इस पाइपलाइन या आपूर्ति लाइन के लिए स्वीकृत कार्य आदेश / निविदा की प्रति", "इस लाइन के लिए रखरखाव और निरीक्षण लॉग", "इस आपूर्ति क्षेत्र के लिए जल गुणवत्ता जांच रिपोर्ट", "निधि आवंटन बनाम वास्तविक उपयोग का लेखा", "इस वार्ड के लिए जिम्मेदार अधिकारी का नाम और संपर्क"),
        "electricity": ("इस ट्रांसफार्मर या लाइन के लिए रखरखाव / निरीक्षण लॉग", "इस स्थान की शिकायत इतिहास और कार्रवाई रिपोर्ट", "रखरखाव के लिए जिम्मेदार ठेकेदार या अधिकारी का नाम और संपर्क"),
        "sanitation": ("इस वार्ड को कवर करने वाला स्वच्छता अनुबंध / निविदा", "इस क्षेत्र के लिए संग्रहण अनुसूची और अनुपालन लॉग", "इस वार्ड के लिए जिम्मेदार अधिकारी का नाम और संपर्क"),
        "drainage": ("इस नाले के लिए स्वीकृत कार्य आदेश / निविदा की प्रति", "गाद निकासी / रखरखाव अनुसूची और लॉग", "निधि आवंटन बनाम वास्तविक उपयोग का लेखा"),
        "encroachment": ("इस स्थल के सर्वेक्षण / सीमांकन अभिलेख", "जारी किए गए नोटिस और प्रवर्तन कार्रवाई लॉग", "प्रवर्तन के लिए जिम्मेदार अधिकारी का नाम और संपर्क"),
        "police": ("इस मामले से संबंधित एफआईआर / शिकायत रजिस्टर प्रविष्टि, यदि कोई हो", "फाइल पर दर्ज कार्रवाई रिपोर्ट", "इस क्षेत्र को सौंपे गए गश्ती / बीट अधिकारी का नाम"),
        "other": ("इस मामले पर संबंधित फाइल टिप्पणियां और पत्राचार", "जिम्मेदार अधिकारी का नाम और संपर्क", "फाइल पर दर्ज कार्रवाई रिपोर्ट, यदि कोई हो"),
    },
    "mr": {
        "roads": ("या रस्त्याच्या भागासाठी मंजूर कार्यादेश / निविदेची प्रत", "तांत्रिक मंजुरी आणि सविस्तर अंदाजपत्रक", "या कामासाठी नोंदवलेल्या मोजमाप पुस्तिका (एमबी) नोंदी", "वापरलेल्या साहित्याच्या गुणवत्ता चाचणी / प्रयोगशाळा ताकद अहवाल", "निधी वाटप विरुद्ध प्रत्यक्ष वापर लेखा", "स्थळ तपासणीसाठी जबाबदार अभियंत्याचे नाव आणि संपर्क"),
        "water": ("या पाइपलाइन किंवा पुरवठा लाइनसाठी मंजूर कार्यादेश / निविदेची प्रत", "या लाइनसाठी देखभाल आणि तपासणी नोंदवही", "या पुरवठा क्षेत्रासाठी पाणी गुणवत्ता चाचणी अहवाल", "निधी वाटप विरुद्ध प्रत्यक्ष वापर लेखा", "या वॉर्डसाठी जबाबदार अधिकाऱ्याचे नाव आणि संपर्क"),
        "electricity": ("या ट्रान्सफॉर्मर किंवा लाइनसाठी देखभाल / तपासणी नोंदवही", "या ठिकाणाचा तक्रार इतिहास आणि कृती अहवाल", "देखभालीसाठी जबाबदार कंत्राटदार किंवा अधिकाऱ्याचे नाव आणि संपर्क"),
        "sanitation": ("या वॉर्डला व्यापणारा स्वच्छता करार / निविदा", "या भागासाठी संकलन वेळापत्रक आणि अनुपालन नोंदवही", "या वॉर्डसाठी जबाबदार अधिकाऱ्याचे नाव आणि संपर्क"),
        "drainage": ("या गटारासाठी मंजूर कार्यादेश / निविदेची प्रत", "गाळ काढणे / देखभाल वेळापत्रक आणि नोंदवही", "निधी वाटप विरुद्ध प्रत्यक्ष वापर लेखा"),
        "encroachment": ("या जागेच्या सर्वेक्षण / सीमांकन नोंदी", "जारी केलेल्या नोटिसा आणि अंमलबजावणी कृती नोंदवही", "अंमलबजावणीसाठी जबाबदार अधिकाऱ्याचे नाव आणि संपर्क"),
        "police": ("या प्रकरणाशी संबंधित एफआयआर / तक्रार नोंदवही नोंद, असल्यास", "फाइलवरील नोंदवलेला कृती अहवाल", "या भागाला नेमलेल्या गस्त / बीट अधिकाऱ्याचे नाव"),
        "other": ("या प्रकरणाशी संबंधित फाइल नोंदी आणि पत्रव्यवहार", "जबाबदार अधिकाऱ्याचे नाव आणि संपर्क", "फाइलवरील नोंदवलेला कृती अहवाल, असल्यास"),
    },
    "bn": {
        "roads": ("এই রাস্তার অংশের জন্য অনুমোদিত কার্যাদেশ / দরপত্রের অনুলিপি", "প্রযুক্তিগত অনুমোদন এবং বিস্তারিত প্রাক্কলন", "এই কাজের জন্য নথিভুক্ত পরিমাপ বই (এমবি) এন্ট্রি", "ব্যবহৃত উপকরণের গুণমান পরীক্ষা / পরীক্ষাগার শক্তি প্রতিবেদন", "তহবিল বরাদ্দ বনাম প্রকৃত ব্যবহারের হিসাব", "সাইট পরিদর্শনের জন্য দায়ী প্রকৌশলীর নাম ও যোগাযোগ"),
        "water": ("এই পাইপলাইন বা সরবরাহ লাইনের জন্য অনুমোদিত কার্যাদেশ / দরপত্রের অনুলিপি", "এই লাইনের জন্য রক্ষণাবেক্ষণ ও পরিদর্শন লগ", "এই সরবরাহ অঞ্চলের জন্য পানির গুণমান পরীক্ষার প্রতিবেদন", "তহবিল বরাদ্দ বনাম প্রকৃত ব্যবহারের হিসাব", "এই ওয়ার্ডের জন্য দায়ী কর্মকর্তার নাম ও যোগাযোগ"),
        "electricity": ("এই ট্রান্সফরমার বা লাইনের জন্য রক্ষণাবেক্ষণ / পরিদর্শন লগ", "এই স্থানের অভিযোগের ইতিহাস ও গৃহীত ব্যবস্থার প্রতিবেদন", "রক্ষণাবেক্ষণের জন্য দায়ী ঠিকাদার বা কর্মকর্তার নাম ও যোগাযোগ"),
        "sanitation": ("এই ওয়ার্ড কভার করা পরিচ্ছন্নতা চুক্তি / দরপত্র", "এই এলাকার সংগ্রহ সময়সূচি ও কমপ্লায়েন্স লগ", "এই ওয়ার্ডের জন্য দায়ী কর্মকর্তার নাম ও যোগাযোগ"),
        "drainage": ("এই নর্দমার জন্য অনুমোদিত কার্যাদেশ / দরপত্রের অনুলিপি", "পলি অপসারণ / রক্ষণাবেক্ষণ সময়সূচি ও লগ", "তহবিল বরাদ্দ বনাম প্রকৃত ব্যবহারের হিসাব"),
        "encroachment": ("এই স্থানের জরিপ / সীমানা নির্ধারণ নথি", "জারি করা নোটিশ ও প্রয়োগ ব্যবস্থার লগ", "প্রয়োগের জন্য দায়ী কর্মকর্তার নাম ও যোগাযোগ"),
        "police": ("এই বিষয়ে সংশ্লিষ্ট এফআইআর / অভিযোগ নিবন্ধন এন্ট্রি, যদি থাকে", "ফাইলে থাকা গৃহীত ব্যবস্থার প্রতিবেদন", "এই এলাকায় নিযুক্ত টহল / বিট কর্মকর্তার নাম"),
        "other": ("এই বিষয়ে সংশ্লিষ্ট ফাইল নোট ও চিঠিপত্র", "দায়ী কর্মকর্তার নাম ও যোগাযোগ", "ফাইলে থাকা গৃহীত ব্যবস্থার প্রতিবেদন, যদি থাকে"),
    },
    "gu": {
        "roads": ("આ રસ્તાના ભાગ માટે મંજૂર કાર્યાદેશ / ટેન્ડરની નકલ", "ટેકનિકલ મંજૂરી અને વિગતવાર અંદાજ", "આ કામ માટે નોંધાયેલ માપણી પુસ્તિકા (એમબી) એન્ટ્રીઓ", "વપરાયેલ સામગ્રીના ગુણવત્તા પરીક્ષણ / લેબ મજબૂતાઈ અહેવાલો", "ભંડોળ ફાળવણી વિરુદ્ધ વાસ્તવિક ઉપયોગનો હિસાબ", "સાઇટ નિરીક્ષણ માટે જવાબદાર ઇજનેરનું નામ અને સંપર્ક"),
        "water": ("આ પાઇપલાઇન અથવા સપ્લાય લાઇન માટે મંજૂર કાર્યાદેશ / ટેન્ડરની નકલ", "આ લાઇન માટે જાળવણી અને નિરીક્ષણ લોગ", "આ સપ્લાય ઝોન માટે પાણીની ગુણવત્તા પરીક્ષણ અહેવાલો", "ભંડોળ ફાળવણી વિરુદ્ધ વાસ્તવિક ઉપયોગનો હિસાબ", "આ વોર્ડ માટે જવાબદાર અધિકારીનું નામ અને સંપર્ક"),
        "electricity": ("આ ટ્રાન્સફોર્મર અથવા લાઇન માટે જાળવણી / નિરીક્ષણ લોગ", "આ સ્થળનો ફરિયાદ ઇતિહાસ અને લેવાયેલા પગલાંના અહેવાલો", "જાળવણી માટે જવાબદાર કોન્ટ્રાક્ટર અથવા અધિકારીનું નામ અને સંપર્ક"),
        "sanitation": ("આ વોર્ડને આવરી લેતો સ્વચ્છતા કરાર / ટેન્ડર", "આ વિસ્તાર માટે સંગ્રહ સમયપત્રક અને પાલન લોગ", "આ વોર્ડ માટે જવાબદાર અધિકારીનું નામ અને સંપર્ક"),
        "drainage": ("આ ગટર માટે મંજૂર કાર્યાદેશ / ટેન્ડરની નકલ", "કાદવ દૂર કરવાનું / જાળવણી સમયપત્રક અને લોગ", "ભંડોળ ફાળવણી વિરુદ્ધ વાસ્તવિક ઉપયોગનો હિસાબ"),
        "encroachment": ("આ સ્થળના સર્વે / સીમાંકન રેકોર્ડ", "જારી કરાયેલ નોટિસો અને અમલીકરણ પગલાં લોગ", "અમલીકરણ માટે જવાબદાર અધિકારીનું નામ અને સંપર્ક"),
        "police": ("આ બાબત સંબંધિત એફઆઈઆર / ફરિયાદ રજિસ્ટર એન્ટ્રી, જો હોય તો", "ફાઇલ પર નોંધાયેલ પગલાં અહેવાલ", "આ વિસ્તારને સોંપાયેલ પેટ્રોલ / બીટ અધિકારીનું નામ"),
        "other": ("આ બાબત પર સંબંધિત ફાઇલ નોંધો અને પત્રવ્યવહાર", "જવાબદાર અધિકારીનું નામ અને સંપર્ક", "ફાઇલ પર નોંધાયેલ પગલાં અહેવાલ, જો હોય તો"),
    },
    "pa": {
        "roads": ("ਇਸ ਸੜਕ ਹਿੱਸੇ ਲਈ ਮਨਜ਼ੂਰਸ਼ੁਦਾ ਕੰਮ ਆਦੇਸ਼ / ਟੈਂਡਰ ਦੀ ਕਾਪੀ", "ਤਕਨੀਕੀ ਮਨਜ਼ੂਰੀ ਅਤੇ ਵਿਸਤ੍ਰਿਤ ਅਨੁਮਾਨ", "ਇਸ ਕੰਮ ਲਈ ਦਰਜ ਮਾਪ ਪੁਸਤਕ (ਐਮਬੀ) ਐਂਟਰੀਆਂ", "ਵਰਤੀ ਗਈ ਸਮੱਗਰੀ ਦੀ ਗੁਣਵੱਤਾ ਜਾਂਚ / ਲੈਬ ਤਾਕਤ ਰਿਪੋਰਟਾਂ", "ਫੰਡ ਅਲਾਟਮੈਂਟ ਬਨਾਮ ਅਸਲ ਵਰਤੋਂ ਦਾ ਲੇਖਾ", "ਸਾਈਟ ਨਿਰੀਖਣ ਲਈ ਜ਼ਿੰਮੇਵਾਰ ਇੰਜੀਨੀਅਰ ਦਾ ਨਾਮ ਅਤੇ ਸੰਪਰਕ"),
        "water": ("ਇਸ ਪਾਈਪਲਾਈਨ ਜਾਂ ਸਪਲਾਈ ਲਾਈਨ ਲਈ ਮਨਜ਼ੂਰਸ਼ੁਦਾ ਕੰਮ ਆਦੇਸ਼ / ਟੈਂਡਰ ਦੀ ਕਾਪੀ", "ਇਸ ਲਾਈਨ ਲਈ ਸਾਂਭ-ਸੰਭਾਲ ਅਤੇ ਨਿਰੀਖਣ ਲੌਗ", "ਇਸ ਸਪਲਾਈ ਜ਼ੋਨ ਲਈ ਪਾਣੀ ਦੀ ਗੁਣਵੱਤਾ ਜਾਂਚ ਰਿਪੋਰਟਾਂ", "ਫੰਡ ਅਲਾਟਮੈਂਟ ਬਨਾਮ ਅਸਲ ਵਰਤੋਂ ਦਾ ਲੇਖਾ", "ਇਸ ਵਾਰਡ ਲਈ ਜ਼ਿੰਮੇਵਾਰ ਅਧਿਕਾਰੀ ਦਾ ਨਾਮ ਅਤੇ ਸੰਪਰਕ"),
        "electricity": ("ਇਸ ਟ੍ਰਾਂਸਫਾਰਮਰ ਜਾਂ ਲਾਈਨ ਲਈ ਸਾਂਭ-ਸੰਭਾਲ / ਨਿਰੀਖਣ ਲੌਗ", "ਇਸ ਸਥਾਨ ਦਾ ਸ਼ਿਕਾਇਤ ਇਤਿਹਾਸ ਅਤੇ ਕਾਰਵਾਈ ਰਿਪੋਰਟਾਂ", "ਸਾਂਭ-ਸੰਭਾਲ ਲਈ ਜ਼ਿੰਮੇਵਾਰ ਠੇਕੇਦਾਰ ਜਾਂ ਅਧਿਕਾਰੀ ਦਾ ਨਾਮ ਅਤੇ ਸੰਪਰਕ"),
        "sanitation": ("ਇਸ ਵਾਰਡ ਨੂੰ ਕਵਰ ਕਰਨ ਵਾਲਾ ਸਵੱਛਤਾ ਇਕਰਾਰਨਾਮਾ / ਟੈਂਡਰ", "ਇਸ ਖੇਤਰ ਲਈ ਇਕੱਤਰੀਕਰਨ ਸਮਾਂ-ਸਾਰਣੀ ਅਤੇ ਪਾਲਣਾ ਲੌਗ", "ਇਸ ਵਾਰਡ ਲਈ ਜ਼ਿੰਮੇਵਾਰ ਅਧਿਕਾਰੀ ਦਾ ਨਾਮ ਅਤੇ ਸੰਪਰਕ"),
        "drainage": ("ਇਸ ਨਾਲੇ ਲਈ ਮਨਜ਼ੂਰਸ਼ੁਦਾ ਕੰਮ ਆਦੇਸ਼ / ਟੈਂਡਰ ਦੀ ਕਾਪੀ", "ਗਾਦ ਕੱਢਣ / ਸਾਂਭ-ਸੰਭਾਲ ਸਮਾਂ-ਸਾਰਣੀ ਅਤੇ ਲੌਗ", "ਫੰਡ ਅਲਾਟਮੈਂਟ ਬਨਾਮ ਅਸਲ ਵਰਤੋਂ ਦਾ ਲੇਖਾ"),
        "encroachment": ("ਇਸ ਸਥਾਨ ਦੇ ਸਰਵੇਖਣ / ਹੱਦਬੰਦੀ ਰਿਕਾਰਡ", "ਜਾਰੀ ਕੀਤੇ ਨੋਟਿਸ ਅਤੇ ਲਾਗੂਕਰਨ ਕਾਰਵਾਈ ਲੌਗ", "ਲਾਗੂਕਰਨ ਲਈ ਜ਼ਿੰਮੇਵਾਰ ਅਧਿਕਾਰੀ ਦਾ ਨਾਮ ਅਤੇ ਸੰਪਰਕ"),
        "police": ("ਇਸ ਮਾਮਲੇ ਨਾਲ ਸਬੰਧਤ ਐਫਆਈਆਰ / ਸ਼ਿਕਾਇਤ ਰਜਿਸਟਰ ਐਂਟਰੀ, ਜੇ ਕੋਈ ਹੋਵੇ", "ਫਾਈਲ 'ਤੇ ਦਰਜ ਕਾਰਵਾਈ ਰਿਪੋਰਟ", "ਇਸ ਖੇਤਰ ਨੂੰ ਸੌਂਪੇ ਗਏ ਗਸ਼ਤ / ਬੀਟ ਅਧਿਕਾਰੀ ਦਾ ਨਾਮ"),
        "other": ("ਇਸ ਮਾਮਲੇ ਬਾਰੇ ਸਬੰਧਤ ਫਾਈਲ ਨੋਟਿੰਗਾਂ ਅਤੇ ਪੱਤਰ-ਵਿਹਾਰ", "ਜ਼ਿੰਮੇਵਾਰ ਅਧਿਕਾਰੀ ਦਾ ਨਾਮ ਅਤੇ ਸੰਪਰਕ", "ਫਾਈਲ 'ਤੇ ਦਰਜ ਕਾਰਵਾਈ ਰਿਪੋਰਟ, ਜੇ ਕੋਈ ਹੋਵੇ"),
    },
    "ta": {
        "roads": ("இந்த சாலைப் பகுதிக்கான அங்கீகரிக்கப்பட்ட பணி ஆணை / டெண்டர் நகல்", "தொழில்நுட்ப அனுமதி மற்றும் விரிவான மதிப்பீடு", "இந்த வேலைக்காக பதிவு செய்யப்பட்ட அளவீட்டு புத்தக (எம்பி) பதிவுகள்", "பயன்படுத்தப்பட்ட பொருட்களின் தர சோதனை / ஆய்வக வலிமை அறிக்கைகள்", "நிதி ஒதுக்கீடு எதிராக உண்மையான பயன்பாட்டு கணக்கு", "தள ஆய்வுக்குப் பொறுப்பான பொறியாளரின் பெயர் மற்றும் தொடர்பு"),
        "water": ("இந்த குழாய் அல்லது வழங்கல் கோட்டிற்கான அங்கீகரிக்கப்பட்ட பணி ஆணை / டெண்டர் நகல்", "இந்த கோட்டிற்கான பராமரிப்பு மற்றும் ஆய்வு பதிவேடு", "இந்த வழங்கல் மண்டலத்திற்கான தண்ணீர் தர சோதனை அறிக்கைகள்", "நிதி ஒதுக்கீடு எதிராக உண்மையான பயன்பாட்டு கணக்கு", "இந்த வார்டிற்குப் பொறுப்பான அதிகாரியின் பெயர் மற்றும் தொடர்பு"),
        "electricity": ("இந்த மின்மாற்றி அல்லது கோட்டிற்கான பராமரிப்பு / ஆய்வு பதிவேடு", "இந்த இடத்தின் புகார் வரலாறு மற்றும் நடவடிக்கை அறிக்கைகள்", "பராமரிப்புக்குப் பொறுப்பான ஒப்பந்தக்காரர் அல்லது அதிகாரியின் பெயர் மற்றும் தொடர்பு"),
        "sanitation": ("இந்த வார்டை உள்ளடக்கிய தூய்மைப்பணி ஒப்பந்தம் / டெண்டர்", "இந்த பகுதிக்கான சேகரிப்பு அட்டவணை மற்றும் இணக்க பதிவேடு", "இந்த வார்டிற்குப் பொறுப்பான அதிகாரியின் பெயர் மற்றும் தொடர்பு"),
        "drainage": ("இந்த வடிகாலுக்கான அங்கீகரிக்கப்பட்ட பணி ஆணை / டெண்டர் நகல்", "வண்டல் அகற்றுதல் / பராமரிப்பு அட்டவணை மற்றும் பதிவேடு", "நிதி ஒதுக்கீடு எதிராக உண்மையான பயன்பாட்டு கணக்கு"),
        "encroachment": ("இந்த இடத்தின் கணக்கெடுப்பு / எல்லை நிர்ணய பதிவுகள்", "வழங்கப்பட்ட அறிவிப்புகள் மற்றும் அமலாக்க நடவடிக்கை பதிவேடு", "அமலாக்கத்திற்குப் பொறுப்பான அதிகாரியின் பெயர் மற்றும் தொடர்பு"),
        "police": ("இந்த விவகாரம் தொடர்பான எஃப்ஐஆர் / புகார் பதிவேடு உள்ளீடு, இருந்தால்", "கோப்பில் உள்ள நடவடிக்கை அறிக்கை", "இந்த பகுதிக்கு நியமிக்கப்பட்ட ரோந்து / பீட் அதிகாரியின் பெயர்"),
        "other": ("இந்த விவகாரம் தொடர்பான கோப்பு குறிப்புகள் மற்றும் கடிதப் பரிமாற்றம்", "பொறுப்பான அதிகாரியின் பெயர் மற்றும் தொடர்பு", "கோப்பில் உள்ள நடவடிக்கை அறிக்கை, இருந்தால்"),
    },
    "te": {
        "roads": ("ఈ రోడ్డు భాగానికి మంజూరైన వర్క్ ఆర్డర్ / టెండర్ ప్రతి", "సాంకేతిక అనుమతి మరియు వివరణాత్మక అంచనా", "ఈ పని కోసం నమోదైన కొలత పుస్తక (ఎంబి) ఎంట్రీలు", "ఉపయోగించిన సామగ్రి నాణ్యత పరీక్ష / ల్యాబ్ బలం నివేదికలు", "నిధుల కేటాయింపు వర్సెస్ వాస్తవ వినియోగ లెడ్జర్", "సైట్ తనిఖీకి బాధ్యత వహించే ఇంజనీర్ పేరు మరియు సంప్రదింపు"),
        "water": ("ఈ పైప్‌లైన్ లేదా సరఫరా లైన్‌కు మంజూరైన వర్క్ ఆర్డర్ / టెండర్ ప్రతి", "ఈ లైన్ కోసం నిర్వహణ మరియు తనిఖీ లాగ్", "ఈ సరఫరా మండలానికి నీటి నాణ్యత పరీక్ష నివేదికలు", "నిధుల కేటాయింపు వర్సెస్ వాస్తవ వినియోగ లెడ్జర్", "ఈ వార్డుకు బాధ్యత వహించే అధికారి పేరు మరియు సంప్రదింపు"),
        "electricity": ("ఈ ట్రాన్స్‌ఫార్మర్ లేదా లైన్ కోసం నిర్వహణ / తనిఖీ లాగ్", "ఈ ప్రదేశం యొక్క ఫిర్యాదు చరిత్ర మరియు చర్యల నివేదికలు", "నిర్వహణకు బాధ్యత వహించే కాంట్రాక్టర్ లేదా అధికారి పేరు మరియు సంప్రదింపు"),
        "sanitation": ("ఈ వార్డును కవర్ చేసే పారిశుద్ధ్య ఒప్పందం / టెండర్", "ఈ ప్రాంతానికి సేకరణ షెడ్యూల్ మరియు కంప్లయన్స్ లాగ్", "ఈ వార్డుకు బాధ్యత వహించే అధికారి పేరు మరియు సంప్రదింపు"),
        "drainage": ("ఈ కాలువకు మంజూరైన వర్క్ ఆర్డర్ / టెండర్ ప్రతి", "పూడిక తీయడం / నిర్వహణ షెడ్యూల్ మరియు లాగ్", "నిధుల కేటాయింపు వర్సెస్ వాస్తవ వినియోగ లెడ్జర్"),
        "encroachment": ("ఈ స్థలం యొక్క సర్వే / సరిహద్దు నిర్ధారణ రికార్డులు", "జారీ చేసిన నోటీసులు మరియు అమలు చర్య లాగ్", "అమలుకు బాధ్యత వహించే అధికారి పేరు మరియు సంప్రదింపు"),
        "police": ("ఈ విషయానికి సంబంధించిన ఎఫ్‌ఐఆర్ / ఫిర్యాదు రిజిస్టర్ ఎంట్రీ, ఉంటే", "ఫైల్‌లో ఉన్న చర్యల నివేదిక", "ఈ ప్రాంతానికి కేటాయించిన పెట్రోల్ / బీట్ అధికారి పేరు"),
        "other": ("ఈ విషయానికి సంబంధించిన ఫైల్ నోటింగ్‌లు మరియు ఉత్తర ప్రత్యుత్తరాలు", "బాధ్యత వహించే అధికారి పేరు మరియు సంప్రదింపు", "ఫైల్‌లో ఉన్న చర్యల నివేదిక, ఉంటే"),
    },
    "kn": {
        "roads": ("ಈ ರಸ್ತೆ ವಿಭಾಗಕ್ಕೆ ಮಂಜೂರಾದ ಕಾರ್ಯಾದೇಶ / ಟೆಂಡರ್ ಪ್ರತಿ", "ತಾಂತ್ರಿಕ ಅನುಮೋದನೆ ಮತ್ತು ವಿವರವಾದ ಅಂದಾಜು", "ಈ ಕೆಲಸಕ್ಕಾಗಿ ದಾಖಲಾದ ಅಳತೆ ಪುಸ್ತಕ (ಎಂಬಿ) ನಮೂದುಗಳು", "ಬಳಸಿದ ಸಾಮಗ್ರಿಗಳ ಗುಣಮಟ್ಟ ಪರೀಕ್ಷೆ / ಲ್ಯಾಬ್ ಶಕ್ತಿ ವರದಿಗಳು", "ನಿಧಿ ಹಂಚಿಕೆ ವಿರುದ್ಧ ನಿಜವಾದ ಬಳಕೆಯ ಲೆಡ್ಜರ್", "ಸೈಟ್ ತಪಾಸಣೆಗೆ ಜವಾಬ್ದಾರರಾದ ಎಂಜಿನಿಯರ್‌ ಹೆಸರು ಮತ್ತು ಸಂಪರ್ಕ"),
        "water": ("ಈ ಪೈಪ್‌ಲೈನ್ ಅಥವಾ ಪೂರೈಕೆ ಮಾರ್ಗಕ್ಕೆ ಮಂಜೂರಾದ ಕಾರ್ಯಾದೇಶ / ಟೆಂಡರ್ ಪ್ರತಿ", "ಈ ಮಾರ್ಗಕ್ಕಾಗಿ ನಿರ್ವಹಣೆ ಮತ್ತು ತಪಾಸಣೆ ದಾಖಲೆ", "ಈ ಪೂರೈಕೆ ವಲಯಕ್ಕೆ ನೀರಿನ ಗುಣಮಟ್ಟ ಪರೀಕ್ಷಾ ವರದಿಗಳು", "ನಿಧಿ ಹಂಚಿಕೆ ವಿರುದ್ಧ ನಿಜವಾದ ಬಳಕೆಯ ಲೆಡ್ಜರ್", "ಈ ವಾರ್ಡ್‌ಗೆ ಜವಾಬ್ದಾರರಾದ ಅಧಿಕಾರಿಯ ಹೆಸರು ಮತ್ತು ಸಂಪರ್ಕ"),
        "electricity": ("ಈ ಟ್ರಾನ್ಸ್‌ಫಾರ್ಮರ್ ಅಥವಾ ಮಾರ್ಗಕ್ಕಾಗಿ ನಿರ್ವಹಣೆ / ತಪಾಸಣೆ ದಾಖಲೆ", "ಈ ಸ್ಥಳದ ದೂರು ಇತಿಹಾಸ ಮತ್ತು ಕ್ರಮ ವರದಿಗಳು", "ನಿರ್ವಹಣೆಗೆ ಜವಾಬ್ದಾರರಾದ ಗುತ್ತಿಗೆದಾರ ಅಥವಾ ಅಧಿಕಾರಿಯ ಹೆಸರು ಮತ್ತು ಸಂಪರ್ಕ"),
        "sanitation": ("ಈ ವಾರ್ಡ್ ಅನ್ನು ಒಳಗೊಂಡ ನೈರ್ಮಲ್ಯ ಒಪ್ಪಂದ / ಟೆಂಡರ್", "ಈ ಪ್ರದೇಶಕ್ಕೆ ಸಂಗ್ರಹಣೆ ವೇಳಾಪಟ್ಟಿ ಮತ್ತು ಅನುಸರಣೆ ದಾಖಲೆ", "ಈ ವಾರ್ಡ್‌ಗೆ ಜವಾಬ್ದಾರರಾದ ಅಧಿಕಾರಿಯ ಹೆಸರು ಮತ್ತು ಸಂಪರ್ಕ"),
        "drainage": ("ಈ ಚರಂಡಿಗೆ ಮಂಜೂರಾದ ಕಾರ್ಯಾದೇಶ / ಟೆಂಡರ್ ಪ್ರತಿ", "ಹೂಳು ತೆಗೆಯುವಿಕೆ / ನಿರ್ವಹಣೆ ವೇಳಾಪಟ್ಟಿ ಮತ್ತು ದಾಖಲೆ", "ನಿಧಿ ಹಂಚಿಕೆ ವಿರುದ್ಧ ನಿಜವಾದ ಬಳಕೆಯ ಲೆಡ್ಜರ್"),
        "encroachment": ("ಈ ಸ್ಥಳದ ಸಮೀಕ್ಷೆ / ಗಡಿ ಗುರುತಿಸುವಿಕೆ ದಾಖಲೆಗಳು", "ನೀಡಲಾದ ನೋಟಿಸ್‌ಗಳು ಮತ್ತು ಜಾರಿ ಕ್ರಮ ದಾಖಲೆ", "ಜಾರಿಗೆ ಜವಾಬ್ದಾರರಾದ ಅಧಿಕಾರಿಯ ಹೆಸರು ಮತ್ತು ಸಂಪರ್ಕ"),
        "police": ("ಈ ವಿಷಯಕ್ಕೆ ಸಂಬಂಧಿಸಿದ ಎಫ್‌ಐಆರ್ / ದೂರು ನೋಂದಣಿ ನಮೂದು, ಇದ್ದರೆ", "ಫೈಲ್‌ನಲ್ಲಿರುವ ಕ್ರಮ ವರದಿ", "ಈ ಪ್ರದೇಶಕ್ಕೆ ನಿಯೋಜಿಸಲಾದ ಗಸ್ತು / ಬೀಟ್ ಅಧಿಕಾರಿಯ ಹೆಸರು"),
        "other": ("ಈ ವಿಷಯದ ಬಗ್ಗೆ ಸಂಬಂಧಿಸಿದ ಫೈಲ್ ಟಿಪ್ಪಣಿಗಳು ಮತ್ತು ಪತ್ರವ್ಯವಹಾರ", "ಜವಾಬ್ದಾರರಾದ ಅಧಿಕಾರಿಯ ಹೆಸರು ಮತ್ತು ಸಂಪರ್ಕ", "ಫೈಲ್‌ನಲ್ಲಿರುವ ಕ್ರಮ ವರದಿ, ಇದ್ದರೆ"),
    },
    "ml": {
        "roads": ("ഈ റോഡ് ഭാഗത്തിന് അനുവദിച്ച വർക്ക് ഓർഡർ / ടെൻഡർ പകർപ്പ്", "സാങ്കേതിക അനുമതിയും വിശദമായ എസ്റ്റിമേറ്റും", "ഈ ജോലിക്കായി രേഖപ്പെടുത്തിയ അളവ് പുസ്തക (എംബി) എൻട്രികൾ", "ഉപയോഗിച്ച വസ്തുക്കളുടെ ഗുണനിലവാര പരിശോധന / ലാബ് ശക്തി റിപ്പോർട്ടുകൾ", "ഫണ്ട് വിഹിതം vs യഥാർത്ഥ വിനിയോഗ കണക്ക്", "സൈറ്റ് പരിശോധനയ്ക്ക് ഉത്തരവാദിയായ എഞ്ചിനീയറുടെ പേരും ബന്ധപ്പെടലും"),
        "water": ("ഈ പൈപ്പ്‌ലൈൻ അല്ലെങ്കിൽ വിതരണ ലൈനിന് അനുവദിച്ച വർക്ക് ഓർഡർ / ടെൻഡർ പകർപ്പ്", "ഈ ലൈനിനുള്ള അറ്റകുറ്റപ്പണി, പരിശോധന ലോഗ്", "ഈ വിതരണ മേഖലയ്ക്കുള്ള ജല ഗുണനിലവാര പരിശോധന റിപ്പോർട്ടുകൾ", "ഫണ്ട് വിഹിതം vs യഥാർത്ഥ വിനിയോഗ കണക്ക്", "ഈ വാർഡിന് ഉത്തരവാദിയായ ഉദ്യോഗസ്ഥന്റെ പേരും ബന്ധപ്പെടലും"),
        "electricity": ("ഈ ട്രാൻസ്ഫോർമർ അല്ലെങ്കിൽ ലൈനിനുള്ള അറ്റകുറ്റപ്പണി / പരിശോധന ലോഗ്", "ഈ സ്ഥലത്തിന്റെ പരാതി ചരിത്രവും നടപടി റിപ്പോർട്ടുകളും", "അറ്റകുറ്റപ്പണിക്ക് ഉത്തരവാദിയായ കരാറുകാരന്റെയോ ഉദ്യോഗസ്ഥന്റെയോ പേരും ബന്ധപ്പെടലും"),
        "sanitation": ("ഈ വാർഡ് ഉൾക്കൊള്ളുന്ന ശുചീകരണ കരാർ / ടെൻഡർ", "ഈ പ്രദേശത്തിനുള്ള ശേഖരണ ഷെഡ്യൂളും അനുസരണ ലോഗും", "ഈ വാർഡിന് ഉത്തരവാദിയായ ഉദ്യോഗസ്ഥന്റെ പേരും ബന്ധപ്പെടലും"),
        "drainage": ("ഈ ഓടയ്ക്ക് അനുവദിച്ച വർക്ക് ഓർഡർ / ടെൻഡർ പകർപ്പ്", "ചെളി നീക്കൽ / അറ്റകുറ്റപ്പണി ഷെഡ്യൂളും ലോഗും", "ഫണ്ട് വിഹിതം vs യഥാർത്ഥ വിനിയോഗ കണക്ക്"),
        "encroachment": ("ഈ സ്ഥലത്തിന്റെ സർവേ / അതിർത്തി നിർണ്ണയ രേഖകൾ", "നൽകിയ നോട്ടീസുകളും നടപടി ലോഗും", "നടപടിക്ക് ഉത്തരവാദിയായ ഉദ്യോഗസ്ഥന്റെ പേരും ബന്ധപ്പെടലും"),
        "police": ("ഈ വിഷയവുമായി ബന്ധപ്പെട്ട എഫ്ഐആർ / പരാതി രജിസ്റ്റർ എൻട്രി, ഉണ്ടെങ്കിൽ", "ഫയലിലുള്ള നടപടി റിപ്പോർട്ട്", "ഈ പ്രദേശത്തിന് നിയോഗിക്കപ്പെട്ട പട്രോൾ / ബീറ്റ് ഉദ്യോഗസ്ഥന്റെ പേര്"),
        "other": ("ഈ വിഷയവുമായി ബന്ധപ്പെട്ട ഫയൽ കുറിപ്പുകളും കത്തിടപാടുകളും", "ഉത്തരവാദിയായ ഉദ്യോഗസ്ഥന്റെ പേരും ബന്ധപ്പെടലും", "ഫയലിലുള്ള നടപടി റിപ്പോർട്ട്, ഉണ്ടെങ്കിൽ"),
    },
}


def default_records_for_category(category: str | None, language: str = "en") -> tuple[str, ...]:
    cat = (category or "other").lower()
    localized = RTI_CATEGORY_RECORDS_I18N.get(language)
    if localized and cat in localized:
        return localized[cat]
    return RTI_CATEGORY_RECORDS.get(cat, RTI_CATEGORY_RECORDS["other"])


# The fixed sentence structures build_rti_questions() composes around the citizen's own words
# (subject, location, tender reference, time period are all inserted verbatim, in whatever
# language/script they were typed in). ``location_label``/``period_label`` are single words used
# to build a "(Label: value)" parenthetical - a deliberately simple, unambiguous pattern instead of
# inflecting a full clause per language, since word order for an inserted proper noun differs too
# much across these languages to fold in naturally and safely.
RTI_QUESTION_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "location_label": "Location", "period_label": "Period",
        "work_order_base": 'Certified copy of all sanctioned Work Orders, Technical Sanctions and Tender Estimates for the matter: "{subject}"',
        "tender_ref": "Certified copy of the Contract Agreement, milestone schedule and penalty clauses under Tender / Work Order No: {ref}.",
        "record_copy": "Certified copy of {record}",
        "fallback_record": "Certified copy of the relevant maintenance, inspection or fund-utilisation records for this matter",
        "officer_contact": "Name, designation and official contact (e-mail/phone) of the officer responsible for this matter.",
        "grievance_history": "Certified copy of any citizen grievances received regarding this matter and the Action Taken Report(s) recorded on file.",
    },
    "hi": {
        "location_label": "स्थान", "period_label": "अवधि",
        "work_order_base": 'इस मामले से संबंधित सभी स्वीकृत कार्य आदेशों, तकनीकी स्वीकृतियों और निविदा प्राक्कलनों की प्रमाणित प्रति: "{subject}"',
        "tender_ref": "निविदा/कार्य आदेश संख्या {ref} के अंतर्गत अनुबंध, माइलस्टोन अनुसूची और दंड शर्तों की प्रमाणित प्रति।",
        "record_copy": "{record} की प्रमाणित प्रति",
        "fallback_record": "इस मामले से संबंधित रखरखाव, निरीक्षण या निधि उपयोग से जुड़े अभिलेखों की प्रमाणित प्रति",
        "officer_contact": "इस मामले के लिए जिम्मेदार अधिकारी का नाम, पदनाम और आधिकारिक संपर्क (ईमेल/फोन)।",
        "grievance_history": "इस मामले से संबंधित प्राप्त नागरिक शिकायतों और दर्ज की गई कार्रवाई रिपोर्ट(टों) की प्रमाणित प्रति।",
    },
    "mr": {
        "location_label": "ठिकाण", "period_label": "कालावधी",
        "work_order_base": 'या प्रकरणाशी संबंधित सर्व मंजूर कार्यादेश, तांत्रिक मंजुरी आणि निविदा अंदाजपत्रकांची प्रमाणित प्रत: "{subject}"',
        "tender_ref": "निविदा/कार्यादेश क्रमांक {ref} अंतर्गत कराराची, टप्पानिहाय वेळापत्रकाची आणि दंड अटींची प्रमाणित प्रत.",
        "record_copy": "{record} ची प्रमाणित प्रत",
        "fallback_record": "या प्रकरणाशी संबंधित देखभाल, तपासणी किंवा निधी वापराच्या नोंदींची प्रमाणित प्रत",
        "officer_contact": "या प्रकरणासाठी जबाबदार अधिकाऱ्याचे नाव, पदनाम आणि अधिकृत संपर्क (ईमेल/फोन).",
        "grievance_history": "या प्रकरणाशी संबंधित प्राप्त नागरी तक्रारी आणि नोंदवलेल्या कृती अहवालांची प्रमाणित प्रत.",
    },
    "bn": {
        "location_label": "অবস্থান", "period_label": "সময়কাল",
        "work_order_base": 'এই বিষয়ে সংশ্লিষ্ট সকল অনুমোদিত কার্যাদেশ, প্রযুক্তিগত অনুমোদন এবং দরপত্র প্রাক্কলনের প্রত্যয়িত অনুলিপি: "{subject}"',
        "tender_ref": "দরপত্র/কার্যাদেশ নং {ref}-এর অধীনে চুক্তিপত্র, মাইলফলক সময়সূচি এবং জরিমানা শর্তাবলীর প্রত্যয়িত অনুলিপি।",
        "record_copy": "{record}-এর প্রত্যয়িত অনুলিপি",
        "fallback_record": "এই বিষয়ে সংশ্লিষ্ট রক্ষণাবেক্ষণ, পরিদর্শন বা তহবিল ব্যবহার সংক্রান্ত নথির প্রত্যয়িত অনুলিপি",
        "officer_contact": "এই বিষয়ের জন্য দায়ী কর্মকর্তার নাম, পদবি এবং সরকারি যোগাযোগ (ইমেল/ফোন)।",
        "grievance_history": "এই বিষয়ে প্রাপ্ত নাগরিক অভিযোগ এবং নথিভুক্ত ব্যবস্থা গ্রহণ প্রতিবেদনের প্রত্যয়িত অনুলিপি।",
    },
    "gu": {
        "location_label": "સ્થળ", "period_label": "સમયગાળો",
        "work_order_base": 'આ બાબત સાથે સંબંધિત તમામ મંજૂર કાર્યાદેશો, ટેકનિકલ મંજૂરીઓ અને ટેન્ડર અંદાજોની પ્રમાણિત નકલ: "{subject}"',
        "tender_ref": "ટેન્ડર/કાર્યાદેશ ક્રમાંક {ref} હેઠળના કરાર, માઇલસ્ટોન સમયપત્રક અને દંડની શરતોની પ્રમાણિત નકલ.",
        "record_copy": "{record}ની પ્રમાણિત નકલ",
        "fallback_record": "આ બાબત સાથે સંબંધિત જાળવણી, નિરીક્ષણ અથવા ભંડોળ ઉપયોગના રેકોર્ડની પ્રમાણિત નકલ",
        "officer_contact": "આ બાબત માટે જવાબદાર અધિકારીનું નામ, હોદ્દો અને સત્તાવાર સંપર્ક (ઇમેઇલ/ફોન).",
        "grievance_history": "આ બાબત અંગે મળેલી નાગરિક ફરિયાદો અને નોંધાયેલા પગલાં અહેવાલોની પ્રમાણિત નકલ.",
    },
    "pa": {
        "location_label": "ਸਥਾਨ", "period_label": "ਸਮਾਂ-ਮਿਆਦ",
        "work_order_base": 'ਇਸ ਮਾਮਲੇ ਨਾਲ ਸਬੰਧਤ ਸਾਰੇ ਮਨਜ਼ੂਰਸ਼ੁਦਾ ਕੰਮ ਆਦੇਸ਼ਾਂ, ਤਕਨੀਕੀ ਮਨਜ਼ੂਰੀਆਂ ਅਤੇ ਟੈਂਡਰ ਅਨੁਮਾਨਾਂ ਦੀ ਪ੍ਰਮਾਣਿਤ ਕਾਪੀ: "{subject}"',
        "tender_ref": "ਟੈਂਡਰ/ਕੰਮ ਆਦੇਸ਼ ਨੰਬਰ {ref} ਅਧੀਨ ਇਕਰਾਰਨਾਮਾ, ਮੀਲਪੱਥਰ ਸਮਾਂ-ਸਾਰਣੀ ਅਤੇ ਜੁਰਮਾਨਾ ਸ਼ਰਤਾਂ ਦੀ ਪ੍ਰਮਾਣਿਤ ਕਾਪੀ।",
        "record_copy": "{record} ਦੀ ਪ੍ਰਮਾਣਿਤ ਕਾਪੀ",
        "fallback_record": "ਇਸ ਮਾਮਲੇ ਨਾਲ ਸਬੰਧਤ ਸਾਂਭ-ਸੰਭਾਲ, ਨਿਰੀਖਣ ਜਾਂ ਫੰਡ ਵਰਤੋਂ ਦੇ ਰਿਕਾਰਡਾਂ ਦੀ ਪ੍ਰਮਾਣਿਤ ਕਾਪੀ",
        "officer_contact": "ਇਸ ਮਾਮਲੇ ਲਈ ਜ਼ਿੰਮੇਵਾਰ ਅਧਿਕਾਰੀ ਦਾ ਨਾਮ, ਅਹੁਦਾ ਅਤੇ ਅਧਿਕਾਰਤ ਸੰਪਰਕ (ਈਮੇਲ/ਫੋਨ)।",
        "grievance_history": "ਇਸ ਮਾਮਲੇ ਬਾਰੇ ਪ੍ਰਾਪਤ ਨਾਗਰਿਕ ਸ਼ਿਕਾਇਤਾਂ ਅਤੇ ਦਰਜ ਕੀਤੀਆਂ ਕਾਰਵਾਈ ਰਿਪੋਰਟਾਂ ਦੀ ਪ੍ਰਮਾਣਿਤ ਕਾਪੀ।",
    },
    "ta": {
        "location_label": "இடம்", "period_label": "காலம்",
        "work_order_base": 'இந்த விவகாரம் தொடர்பான அனைத்து அங்கீகரிக்கப்பட்ட பணி ஆணைகள், தொழில்நுட்ப அனுமதிகள் மற்றும் டெண்டர் மதிப்பீடுகளின் சான்றளிக்கப்பட்ட நகல்: "{subject}"',
        "tender_ref": "டெண்டர்/பணி ஆணை எண் {ref}-இன் கீழ் ஒப்பந்தம், மைல்கல் அட்டவணை மற்றும் அபராத விதிமுறைகளின் சான்றளிக்கப்பட்ட நகல்.",
        "record_copy": "{record}-இன் சான்றளிக்கப்பட்ட நகல்",
        "fallback_record": "இந்த விவகாரம் தொடர்பான பராமரிப்பு, ஆய்வு அல்லது நிதி பயன்பாடு தொடர்பான ஆவணங்களின் சான்றளிக்கப்பட்ட நகல்",
        "officer_contact": "இந்த விவகாரத்திற்குப் பொறுப்பான அதிகாரியின் பெயர், பதவி மற்றும் அதிகாரப்பூர்வ தொடர்பு (மின்னஞ்சல்/தொலைபேசி).",
        "grievance_history": "இந்த விவகாரம் தொடர்பாக பெறப்பட்ட குடிமக்கள் புகார்கள் மற்றும் பதிவு செய்யப்பட்ட நடவடிக்கை அறிக்கை(கள்)-இன் சான்றளிக்கப்பட்ட நகல்.",
    },
    "te": {
        "location_label": "ప్రదేశం", "period_label": "కాలవ్యవధి",
        "work_order_base": 'ఈ విషయానికి సంబంధించిన అన్ని మంజూరైన వర్క్ ఆర్డర్‌లు, సాంకేతిక అనుమతులు మరియు టెండర్ అంచనాల ధృవీకరించిన ప్రతి: "{subject}"',
        "tender_ref": "టెండర్/వర్క్ ఆర్డర్ నం. {ref} కింద ఒప్పంద పత్రం, మైలురాయి షెడ్యూల్ మరియు జరిమానా నిబంధనల ధృవీకరించిన ప్రతి.",
        "record_copy": "{record} యొక్క ధృవీకరించిన ప్రతి",
        "fallback_record": "ఈ విషయానికి సంబంధించిన నిర్వహణ, తనిఖీ లేదా నిధుల వినియోగ రికార్డుల ధృవీకరించిన ప్రతి",
        "officer_contact": "ఈ విషయానికి బాధ్యత వహించే అధికారి పేరు, హోదా మరియు అధికారిక సంప్రదింపు (ఇమెయిల్/ఫోన్).",
        "grievance_history": "ఈ విషయానికి సంబంధించి అందిన పౌర ఫిర్యాదులు మరియు నమోదు చేయబడిన చర్యల నివేదిక(ల) ధృవీకరించిన ప్రతి.",
    },
    "kn": {
        "location_label": "ಸ್ಥಳ", "period_label": "ಅವಧಿ",
        "work_order_base": 'ಈ ವಿಷಯಕ್ಕೆ ಸಂಬಂಧಿಸಿದ ಎಲ್ಲಾ ಮಂಜೂರಾದ ಕಾರ್ಯಾದೇಶಗಳು, ತಾಂತ್ರಿಕ ಅನುಮೋದನೆಗಳು ಮತ್ತು ಟೆಂಡರ್ ಅಂದಾಜುಗಳ ದೃಢೀಕೃತ ಪ್ರತಿ: "{subject}"',
        "tender_ref": "ಟೆಂಡರ್/ಕಾರ್ಯಾದೇಶ ಸಂಖ್ಯೆ {ref} ಅಡಿಯಲ್ಲಿ ಒಪ್ಪಂದ, ಮೈಲಿಗಲ್ಲು ವೇಳಾಪಟ್ಟಿ ಮತ್ತು ದಂಡದ ಷರತ್ತುಗಳ ದೃಢೀಕೃತ ಪ್ರತಿ.",
        "record_copy": "{record}ದ ದೃಢೀಕೃತ ಪ್ರತಿ",
        "fallback_record": "ಈ ವಿಷಯಕ್ಕೆ ಸಂಬಂಧಿಸಿದ ನಿರ್ವಹಣೆ, ತಪಾಸಣೆ ಅಥವಾ ನಿಧಿ ಬಳಕೆಯ ದಾಖಲೆಗಳ ದೃಢೀಕೃತ ಪ್ರತಿ",
        "officer_contact": "ಈ ವಿಷಯಕ್ಕೆ ಜವಾಬ್ದಾರರಾದ ಅಧಿಕಾರಿಯ ಹೆಸರು, ಹುದ್ದೆ ಮತ್ತು ಅಧಿಕೃತ ಸಂಪರ್ಕ (ಇಮೇಲ್/ಫೋನ್).",
        "grievance_history": "ಈ ವಿಷಯಕ್ಕೆ ಸಂಬಂಧಿಸಿದಂತೆ ಸ್ವೀಕರಿಸಿದ ನಾಗರಿಕ ದೂರುಗಳು ಮತ್ತು ದಾಖಲಿಸಲಾದ ಕ್ರಮ ವರದಿ(ಗಳ) ದೃಢೀಕೃತ ಪ್ರತಿ.",
    },
    "ml": {
        "location_label": "സ്ഥലം", "period_label": "കാലയളവ്",
        "work_order_base": 'ഈ വിഷയവുമായി ബന്ധപ്പെട്ട എല്ലാ അനുവദിച്ച വർക്ക് ഓർഡറുകൾ, സാങ്കേതിക അനുമതികൾ, ടെൻഡർ എസ്റ്റിമേറ്റുകൾ എന്നിവയുടെ സാക്ഷ്യപ്പെടുത്തിയ പകർപ്പ്: "{subject}"',
        "tender_ref": "ടെൻഡർ/വർക്ക് ഓർഡർ നമ്പർ {ref} പ്രകാരമുള്ള കരാർ, മൈൽസ്റ്റോൺ ഷെഡ്യൂൾ, പിഴ വ്യവസ്ഥകൾ എന്നിവയുടെ സാക്ഷ്യപ്പെടുത്തിയ പകർപ്പ്.",
        "record_copy": "{record}ന്റെ സാക്ഷ്യപ്പെടുത്തിയ പകർപ്പ്",
        "fallback_record": "ഈ വിഷയവുമായി ബന്ധപ്പെട്ട അറ്റകുറ്റപ്പണി, പരിശോധന അല്ലെങ്കിൽ ഫണ്ട് വിനിയോഗ രേഖകളുടെ സാക്ഷ്യപ്പെടുത്തിയ പകർപ്പ്",
        "officer_contact": "ഈ വിഷയത്തിന് ഉത്തരവാദിയായ ഉദ്യോഗസ്ഥന്റെ പേര്, തസ്തിക, ഔദ്യോഗിക ബന്ധപ്പെടൽ വിവരങ്ങൾ (ഇമെയിൽ/ഫോൺ).",
        "grievance_history": "ഈ വിഷയവുമായി ബന്ധപ്പെട്ട് ലഭിച്ച പൗര പരാതികളുടെയും രേഖപ്പെടുത്തിയ നടപടി റിപ്പോർട്ടു(കളു)ടെയും സാക്ഷ്യപ്പെടുത്തിയ പകർപ്പ്.",
    },
}


def build_rti_questions(
    *,
    subject: str,
    location: str | None = None,
    records_requested: tuple[str, ...] = (),
    tender_reference: str | None = None,
    time_period: str | None = None,
    custom_questions: tuple[str, ...] = (),
    language: str = "en",
) -> tuple[str, ...]:
    """Compose precise, numbered RTI particulars instead of leaving the citizen a blank box.

    Selecting records and optionally a tender/work-order reference and time period produces
    specific statutory questions; with nothing selected it falls back to the same general
    questions a well-drafted RTI on this subject would ask. ``custom_questions`` (freeform,
    citizen-authored) are always appended, never replaced. The fixed sentence structures are
    rendered in ``language`` from ``RTI_QUESTION_TEMPLATES`` (falling back to English); the
    citizen's own words - subject, location, tender reference, time period, custom questions -
    are always inserted exactly as given.
    """
    t = RTI_QUESTION_TEMPLATES.get(language, RTI_QUESTION_TEMPLATES["en"])
    where = f' ({t["location_label"]}: "{location.strip()}")' if location and location.strip() else ""
    period_suffix = f' ({t["period_label"]}: {time_period.strip()})' if time_period and time_period.strip() else ""
    qs: list[str] = [f'{t["work_order_base"].format(subject=subject.strip())}{where}.']
    if tender_reference and tender_reference.strip():
        qs.append(t["tender_ref"].format(ref=tender_reference.strip()))
    if records_requested:
        qs += [f'{t["record_copy"].format(record=r.strip().rstrip(".").rstrip("।"))}{period_suffix}.' for r in records_requested if r and r.strip()]
    else:
        qs.append(f'{t["fallback_record"]}{period_suffix}.')
    qs.append(t["officer_contact"])
    qs.append(t["grievance_history"])
    qs += [q.strip() for q in custom_questions if q and q.strip()]
    return tuple(qs)


class _ChatProvider(Protocol):
    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.0) -> str: ...


def enhance_questions_with_llm(subject: str, location: str | None, baseline: tuple[str, ...], llm: _ChatProvider | None, language: str = "en") -> tuple[str, ...]:
    """Best-effort: ask the model for 1-3 questions specific to this exact situation, on top of the
    deterministic statutory baseline. Never replaces the baseline, never blocks on failure - an LLM
    outage or a bad response just means the citizen gets the same solid template as before, not an
    error. The model is asked to request information/records only, never to assert facts about the
    matter it wasn't given - it has no factual basis to add beyond what the citizen already wrote.
    ``language`` is the citizen's chosen RTI language - the model is told to reply in it, so its
    additions read consistently with the rest of the (separately, statically translated) letter.
    """
    if llm is None or not subject.strip():
        return baseline
    import json
    import re

    from app.i18n.languages import language_name

    where = f' The location given is: "{location}".' if location else ""
    lang_name = language_name(language)
    prompt = (
        f'A citizen is filing an RTI application about this situation, in their own words: "{subject.strip()[:2000]}"{where}\n\n'
        f"These statutory questions are already included:\n" + "\n".join(f"- {q}" for q in baseline) + "\n\n"
        "Suggest up to 3 ADDITIONAL RTI questions - each requesting a specific document, record or "
        "piece of official information that would help this exact situation, and that is not already "
        "covered above. Do not restate the existing questions. Do not assert or assume any fact "
        "(date, name, amount, cause) that was not stated by the citizen - only request records. "
        f"Write every question in {lang_name}, regardless of what language this instruction is in. "
        'Reply with ONLY a JSON array of strings, e.g. ["question one", "question two"]. If nothing '
        "useful can be added beyond the list above, reply with an empty JSON array []."
    )  # fmt: skip
    try:
        raw = llm.chat([{"role": "user", "content": prompt}], temperature=0.2)
        fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        extra = json.loads(fenced)
        if not isinstance(extra, list):
            return baseline
        cleaned = tuple(q.strip() for q in extra if isinstance(q, str) and q.strip())[:3]
    except Exception:  # noqa: BLE001 - any failure (timeout, bad JSON, provider error) degrades to the deterministic baseline
        return baseline
    return baseline + cleaned


class RtiStatus(StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    FILED = "filed"
    RESPONDED = "responded"
    CLOSED = "closed"


@dataclass(frozen=True)
class RtiRules:
    response_days: int = 30
    life_liberty_hours: int = 48
    reminder_days: tuple[int, ...] = (7, 3, 1, 0)

    def deadline(self, received_at: datetime, *, life_or_liberty: bool) -> datetime:
        if life_or_liberty:
            return received_at + timedelta(hours=self.life_liberty_hours)
        return received_at + timedelta(days=self.response_days)


@dataclass(frozen=True)
class RtiDraft:
    subject: str
    public_authority: str
    questions: tuple[str, ...]
    applicant_name: str
    applicant_address: str
    language: str = "en"
    purpose: str | None = None
    life_or_liberty: bool = False
    below_poverty_line: bool = False
    attachments: tuple[str, ...] = ()


@dataclass
class RtiApplication:
    id: str
    owner_id: str
    draft: RtiDraft
    status: RtiStatus = RtiStatus.DRAFT
    reference: str | None = None
    generated_text: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    filed_at: datetime | None = None
    received_at: datetime | None = None
    due_at: datetime | None = None
    deadline_is_estimate: bool = False
    reminders_sent: tuple[int, ...] = ()


@dataclass(frozen=True)
class Countdown:
    state: str  # "not_started" | "running" | "due_today" | "overdue" | "answered"
    days_remaining: int | None
    hours_remaining: float | None
    due_at: datetime | None
    is_estimate: bool


def validate_draft(d: RtiDraft) -> RtiDraft:
    errors: dict[str, str] = {}
    if not 5 <= len(d.subject.strip()) <= 200:
        errors["subject"] = "Subject must be 5-200 characters."
    if not 3 <= len(d.public_authority.strip()) <= 200:
        errors["public_authority"] = "Name the public authority (3-200 characters)."
    qs = tuple(q.strip() for q in d.questions if q and q.strip())
    if not qs:
        errors["questions"] = "Add at least one question."
    elif len(qs) > MAX_QUESTIONS or any(len(q) > MAX_QUESTION_LEN for q in qs):
        errors["questions"] = f"At most {MAX_QUESTIONS} questions of up to {MAX_QUESTION_LEN} characters."
    if not 2 <= len(d.applicant_name.strip()) <= 120:
        errors["applicant_name"] = "Enter the applicant's name."
    if not 10 <= len(d.applicant_address.strip()) <= 400:
        errors["applicant_address"] = "Enter a postal address (10-400 characters)."
    if errors:
        raise ValidationFailed("The RTI application has errors.", details=errors)
    return replace(d, subject=d.subject.strip(), public_authority=d.public_authority.strip(), questions=qs,
                   applicant_name=d.applicant_name.strip(), applicant_address=d.applicant_address.strip())  # fmt: skip


# The fixed legal boilerplate around the citizen's own words (headers, salutation, deadline/fee/
# exemption sentences), written and maintained here in each supported language - never machine-
# translated at request time, exactly like every other UI string in this project. The citizen's own
# words (subject, questions, context, name, address) are never touched, in whatever language/script
# they were written; only these fixed surrounding sentences change with ``RtiDraft.language``.
RTI_TEMPLATE_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "to": "To,", "pio": "The Public Information Officer,",
        "subject_prefix": "Subject: Request for information under Section 6(1) of the Right to Information Act, 2005 - ",
        "salutation": "Sir/Madam,",
        "request_intro": "I, the undersigned, request the following information under Section 6(1) of the Right to Information Act, 2005:",
        "deadline_standard": "Please provide the information within {days} days (Section 7(1)).",
        "deadline_life": "Please provide the information within {hours} hours (life or liberty, Section 7(1) proviso).",
        "fee_bpl": "I am below the poverty line and am exempt from the application fee under Section 7(5); a copy of my BPL certificate is enclosed.",
        "fee_standard": "The prescribed application fee is being paid as per the applicable rules.",
        "exemption_note": "To the best of my knowledge, the information sought does not fall within the exemptions of Sections 8 and 9 of the Act and relates to your office.",
        "context_prefix": "Context (provided voluntarily; no reason is required under Section 6(2)): ",
        "enclosures_prefix": "Enclosures: ", "closing": "Yours faithfully,",
        "reference_label": "Reference", "date_label": "Date",
    },
    "hi": {
        "to": "सेवा में,", "pio": "जन सूचना अधिकारी,",
        "subject_prefix": "विषय: सूचना का अधिकार अधिनियम, 2005 की धारा 6(1) के अंतर्गत सूचना हेतु आवेदन - ",
        "salutation": "महोदय/महोदया,",
        "request_intro": "मैं, अधोहस्ताक्षरी, सूचना का अधिकार अधिनियम, 2005 की धारा 6(1) के अंतर्गत निम्नलिखित सूचना प्राप्त करना चाहता/चाहती हूँ:",
        "deadline_standard": "कृपया {days} दिनों के भीतर सूचना उपलब्ध कराएं (धारा 7(1))।",
        "deadline_life": "कृपया {hours} घंटों के भीतर सूचना उपलब्ध कराएं (जीवन या स्वतंत्रता से संबंधित, धारा 7(1) परंतुक)।",
        "fee_bpl": "मैं गरीबी रेखा से नीचे (बीपीएल) हूँ और धारा 7(5) के अंतर्गत आवेदन शुल्क से मुक्त हूँ; मेरा बीपीएल प्रमाण पत्र संलग्न है।",
        "fee_standard": "निर्धारित आवेदन शुल्क लागू नियमों के अनुसार अदा किया जा रहा है।",
        "exemption_note": "मेरी जानकारी के अनुसार, मांगी गई सूचना अधिनियम की धारा 8 और 9 के अपवादों के अंतर्गत नहीं आती है और आपके कार्यालय से संबंधित है।",
        "context_prefix": "संदर्भ (स्वेच्छा से दिया गया; धारा 6(2) के अंतर्गत कारण बताना आवश्यक नहीं है): ",
        "enclosures_prefix": "संलग्नक: ", "closing": "भवदीय,",
        "reference_label": "संदर्भ संख्या", "date_label": "दिनांक",
    },
    "mr": {
        "to": "सेवेसी,", "pio": "जन माहिती अधिकारी,",
        "subject_prefix": "विषय: माहितीचा अधिकार अधिनियम, 2005 च्या कलम 6(1) अंतर्गत माहितीसाठी अर्ज - ",
        "salutation": "महोदय/महोदया,",
        "request_intro": "मी, खालील स्वाक्षरीकर्ता, माहितीचा अधिकार अधिनियम, 2005 च्या कलम 6(1) अंतर्गत खालील माहिती मागत आहे:",
        "deadline_standard": "कृपया {days} दिवसांच्या आत माहिती उपलब्ध करून द्यावी (कलम 7(1)).",
        "deadline_life": "कृपया {hours} तासांच्या आत माहिती उपलब्ध करून द्यावी (जीवन किंवा स्वातंत्र्याशी संबंधित, कलम 7(1) परंतुक).",
        "fee_bpl": "मी दारिद्र्यरेषेखालील (बीपीएल) असून कलम 7(5) अंतर्गत अर्ज शुल्कातून सूट मिळण्यास पात्र आहे; माझे बीपीएल प्रमाणपत्र सोबत जोडले आहे.",
        "fee_standard": "विहित अर्ज शुल्क लागू नियमांनुसार भरले जात आहे.",
        "exemption_note": "माझ्या माहितीनुसार, मागितलेली माहिती अधिनियमाच्या कलम 8 आणि 9 मधील अपवादांत येत नाही आणि ती आपल्या कार्यालयाशी संबंधित आहे.",
        "context_prefix": "संदर्भ (ऐच्छिकपणे दिलेला; कलम 6(2) अंतर्गत कारण देणे आवश्यक नाही): ",
        "enclosures_prefix": "जोडपत्रे: ", "closing": "आपला विश्वासू,",
        "reference_label": "संदर्भ क्रमांक", "date_label": "दिनांक",
    },
    "bn": {
        "to": "বরাবর,", "pio": "জন তথ্য আধিকারিক,",
        "subject_prefix": "বিষয়: তথ্যের অধিকার আইন, ২০০৫-এর ধারা ৬(১) অনুসারে তথ্যের জন্য আবেদন - ",
        "salutation": "মহোদয়/মহোদয়া,",
        "request_intro": "আমি, নিম্নস্বাক্ষরকারী, তথ্যের অধিকার আইন, ২০০৫-এর ধারা ৬(১) অনুসারে নিম্নলিখিত তথ্য চাইছি:",
        "deadline_standard": "অনুগ্রহ করে {days} দিনের মধ্যে তথ্য প্রদান করুন (ধারা ৭(১))।",
        "deadline_life": "অনুগ্রহ করে {hours} ঘণ্টার মধ্যে তথ্য প্রদান করুন (জীবন বা স্বাধীনতা সংক্রান্ত, ধারা ৭(১) প্রোভিসো)।",
        "fee_bpl": "আমি দারিদ্র্যসীমার নিচে (বিপিএল) এবং ধারা ৭(৫) অনুসারে আবেদন ফি থেকে অব্যাহতিপ্রাপ্ত; আমার বিপিএল সার্টিফিকেটের একটি কপি সংযুক্ত করা হলো।",
        "fee_standard": "নির্ধারিত আবেদন ফি প্রযোজ্য নিয়ম অনুযায়ী প্রদান করা হচ্ছে।",
        "exemption_note": "আমার জ্ঞান অনুযায়ী, প্রার্থিত তথ্য আইনের ধারা ৮ ও ৯-এর ব্যতিক্রমের আওতায় পড়ে না এবং এটি আপনার কার্যালয়ের সাথে সম্পর্কিত।",
        "context_prefix": "প্রেক্ষাপট (স্বেচ্ছায় প্রদত্ত; ধারা ৬(২) অনুসারে কারণ জানানোর প্রয়োজন নেই): ",
        "enclosures_prefix": "সংযুক্তি: ", "closing": "বিনীত নিবেদক,",
        "reference_label": "রেফারেন্স", "date_label": "তারিখ",
    },
    "gu": {
        "to": "પ્રતિ,", "pio": "જાહેર માહિતી અધિકારી,",
        "subject_prefix": "વિષય: માહિતી અધિકાર અધિનિયમ, 2005ની કલમ 6(1) હેઠળ માહિતી માટે અરજી - ",
        "salutation": "શ્રીમાન/શ્રીમતી,",
        "request_intro": "હું, નીચે સહી કરનાર, માહિતી અધિકાર અધિનિયમ, 2005ની કલમ 6(1) હેઠળ નીચેની માહિતી માંગું છું:",
        "deadline_standard": "કૃપા કરીને {days} દિવસોની અંદર માહિતી પૂરી પાડો (કલમ 7(1)).",
        "deadline_life": "કૃપા કરીને {hours} કલાકોની અંદર માહિતી પૂરી પાડો (જીવન અથવા સ્વતંત્રતા સંબંધિત, કલમ 7(1) પરંતુક).",
        "fee_bpl": "હું ગરીબી રેખા હેઠળ (બીપીએલ) છું અને કલમ 7(5) હેઠળ અરજી ફીમાંથી મુક્તિ ધરાવું છું; મારું બીપીએલ પ્રમાણપત્ર બિડાણ કરેલ છે.",
        "fee_standard": "નિર્ધારિત અરજી ફી લાગુ નિયમો મુજબ ચૂકવવામાં આવી રહી છે.",
        "exemption_note": "મારી જાણકારી મુજબ, માંગેલી માહિતી અધિનિયમની કલમ 8 અને 9ના અપવાદોમાં આવતી નથી અને તે તમારી કચેરી સાથે સંબંધિત છે.",
        "context_prefix": "સંદર્ભ (સ્વૈચ્છિક રીતે આપેલ; કલમ 6(2) હેઠળ કારણ આપવું જરૂરી નથી): ",
        "enclosures_prefix": "બિડાણો: ", "closing": "આપનો વિશ્વાસુ,",
        "reference_label": "સંદર્ભ ક્રમાંક", "date_label": "તારીખ",
    },
    "pa": {
        "to": "ਸੇਵਾ ਵਿਖੇ,", "pio": "ਜਨ ਸੂਚਨਾ ਅਧਿਕਾਰੀ,",
        "subject_prefix": "ਵਿਸ਼ਾ: ਸੂਚਨਾ ਦਾ ਅਧਿਕਾਰ ਐਕਟ, 2005 ਦੀ ਧਾਰਾ 6(1) ਅਧੀਨ ਜਾਣਕਾਰੀ ਲਈ ਬੇਨਤੀ - ",
        "salutation": "ਸ਼੍ਰੀਮਾਨ/ਸ਼੍ਰੀਮਤੀ,",
        "request_intro": "ਮੈਂ, ਹੇਠ ਦਸਤਖਤ ਕਰਨ ਵਾਲਾ/ਵਾਲੀ, ਸੂਚਨਾ ਦਾ ਅਧਿਕਾਰ ਐਕਟ, 2005 ਦੀ ਧਾਰਾ 6(1) ਅਧੀਨ ਹੇਠ ਲਿਖੀ ਜਾਣਕਾਰੀ ਮੰਗਦਾ/ਮੰਗਦੀ ਹਾਂ:",
        "deadline_standard": "ਕਿਰਪਾ ਕਰਕੇ {days} ਦਿਨਾਂ ਦੇ ਅੰਦਰ ਜਾਣਕਾਰੀ ਪ੍ਰਦਾਨ ਕਰੋ (ਧਾਰਾ 7(1))।",
        "deadline_life": "ਕਿਰਪਾ ਕਰਕੇ {hours} ਘੰਟਿਆਂ ਦੇ ਅੰਦਰ ਜਾਣਕਾਰੀ ਪ੍ਰਦਾਨ ਕਰੋ (ਜੀਵਨ ਜਾਂ ਆਜ਼ਾਦੀ ਨਾਲ ਸਬੰਧਤ, ਧਾਰਾ 7(1) ਪਰੰਤੂਕ)।",
        "fee_bpl": "ਮੈਂ ਗਰੀਬੀ ਰੇਖਾ ਤੋਂ ਹੇਠਾਂ (ਬੀਪੀਐਲ) ਹਾਂ ਅਤੇ ਧਾਰਾ 7(5) ਅਧੀਨ ਅਰਜ਼ੀ ਫੀਸ ਤੋਂ ਛੋਟ ਪ੍ਰਾਪਤ ਹਾਂ; ਮੇਰਾ ਬੀਪੀਐਲ ਸਰਟੀਫਿਕੇਟ ਨੱਥੀ ਹੈ।",
        "fee_standard": "ਨਿਰਧਾਰਤ ਅਰਜ਼ੀ ਫੀਸ ਲਾਗੂ ਨਿਯਮਾਂ ਅਨੁਸਾਰ ਅਦਾ ਕੀਤੀ ਜਾ ਰਹੀ ਹੈ।",
        "exemption_note": "ਮੇਰੀ ਜਾਣਕਾਰੀ ਅਨੁਸਾਰ, ਮੰਗੀ ਗਈ ਜਾਣਕਾਰੀ ਐਕਟ ਦੀ ਧਾਰਾ 8 ਅਤੇ 9 ਦੇ ਅਪਵਾਦਾਂ ਅਧੀਨ ਨਹੀਂ ਆਉਂਦੀ ਅਤੇ ਇਹ ਤੁਹਾਡੇ ਦਫ਼ਤਰ ਨਾਲ ਸਬੰਧਤ ਹੈ।",
        "context_prefix": "ਪ੍ਰਸੰਗ (ਸਵੈਇੱਛਤ ਤੌਰ 'ਤੇ ਦਿੱਤਾ ਗਿਆ; ਧਾਰਾ 6(2) ਅਧੀਨ ਕਾਰਨ ਦੱਸਣਾ ਜ਼ਰੂਰੀ ਨਹੀਂ): ",
        "enclosures_prefix": "ਨੱਥੀਆਂ: ", "closing": "ਆਪ ਦਾ ਵਿਸ਼ਵਾਸਪਾਤਰ,",
        "reference_label": "ਹਵਾਲਾ ਨੰਬਰ", "date_label": "ਮਿਤੀ",
    },
    "ta": {
        "to": "பெறுநர்,", "pio": "பொது தகவல் அதிகாரி,",
        "subject_prefix": "பொருள்: தகவல் அறியும் உரிமைச் சட்டம், 2005-இன் பிரிவு 6(1)-இன் கீழ் தகவலுக்கான விண்ணப்பம் - ",
        "salutation": "ஐயா/அம்மா,",
        "request_intro": "கீழே கையொப்பமிடும் நான், தகவல் அறியும் உரிமைச் சட்டம், 2005-இன் பிரிவு 6(1)-இன் கீழ் பின்வரும் தகவலைக் கோருகிறேன்:",
        "deadline_standard": "தயவுசெய்து {days} நாட்களுக்குள் தகவலை வழங்கவும் (பிரிவு 7(1)).",
        "deadline_life": "தயவுசெய்து {hours} மணி நேரத்திற்குள் தகவலை வழங்கவும் (உயிர் அல்லது சுதந்திரம் தொடர்பானது, பிரிவு 7(1) நிபந்தனை).",
        "fee_bpl": "நான் வறுமைக் கோட்டிற்குக் கீழ் (பிபிஎல்) உள்ளவன்/உள்ளவள் என்பதால் பிரிவு 7(5)-இன் கீழ் விண்ணப்பக் கட்டணத்திலிருந்து விலக்கு பெற்றுள்ளேன்; எனது பிபிஎல் சான்றிதழ் இணைக்கப்பட்டுள்ளது.",
        "fee_standard": "நிர்ணயிக்கப்பட்ட விண்ணப்பக் கட்டணம் பொருந்தும் விதிகளின்படி செலுத்தப்படுகிறது.",
        "exemption_note": "எனக்குத் தெரிந்தவரை, கோரப்பட்ட தகவல் சட்டத்தின் பிரிவு 8 மற்றும் 9-இன் விதிவிலக்குகளின் கீழ் வராது மற்றும் இது உங்கள் அலுவலகத்தைச் சார்ந்தது.",
        "context_prefix": "பின்னணி (தானாக முன்வந்து வழங்கப்பட்டது; பிரிவு 6(2)-இன் கீழ் காரணம் தேவையில்லை): ",
        "enclosures_prefix": "இணைப்புகள்: ", "closing": "தங்கள் உண்மையுள்ள,",
        "reference_label": "குறிப்பு எண்", "date_label": "தேதி",
    },
    "te": {
        "to": "సేవలో,", "pio": "పబ్లిక్ ఇన్ఫర్మేషన్ ఆఫీసర్,",
        "subject_prefix": "విషయం: సమాచార హక్కు చట్టం, 2005లోని సెక్షన్ 6(1) ప్రకారం సమాచారం కోసం దరఖాస్తు - ",
        "salutation": "అయ్యా/అమ్మా,",
        "request_intro": "క్రింద సంతకం చేసిన నేను, సమాచార హక్కు చట్టం, 2005లోని సెక్షన్ 6(1) ప్రకారం ఈ క్రింది సమాచారాన్ని కోరుతున్నాను:",
        "deadline_standard": "దయచేసి {days} రోజులలోపు సమాచారాన్ని అందించండి (సెక్షన్ 7(1)).",
        "deadline_life": "దయచేసి {hours} గంటలలోపు సమాచారాన్ని అందించండి (జీవితం లేదా స్వేచ్ఛకు సంబంధించినది, సెక్షన్ 7(1) నిబంధన).",
        "fee_bpl": "నేను దారిద్ర్య రేఖకు దిగువన (బీపీఎల్) ఉన్నాను మరియు సెక్షన్ 7(5) ప్రకారం దరఖాస్తు రుసుము నుండి మినహాయింపు పొందాను; నా బీపీఎల్ ధృవీకరణ పత్రం జతచేయబడింది.",
        "fee_standard": "నిర్ధారిత దరఖాస్తు రుసుము వర్తించే నిబంధనల ప్రకారం చెల్లించబడుతోంది.",
        "exemption_note": "నాకు తెలిసినంత వరకు, కోరిన సమాచారం చట్టంలోని సెక్షన్ 8 మరియు 9 మినహాయింపుల పరిధిలోకి రాదు మరియు ఇది మీ కార్యాలయానికి సంబంధించినది.",
        "context_prefix": "సందర్భం (స్వచ్ఛందంగా అందించబడింది; సెక్షన్ 6(2) ప్రకారం కారణం చెప్పాల్సిన అవసరం లేదు): ",
        "enclosures_prefix": "జతపరుపులు: ", "closing": "మీ విధేయుడు/విధేయురాలు,",
        "reference_label": "సూచన సంఖ్య", "date_label": "తేదీ",
    },
    "kn": {
        "to": "ಸೇವೆಯಲ್ಲಿ,", "pio": "ಸಾರ್ವಜನಿಕ ಮಾಹಿತಿ ಅಧಿಕಾರಿ,",
        "subject_prefix": "ವಿಷಯ: ಮಾಹಿತಿ ಹಕ್ಕು ಕಾಯ್ದೆ, 2005ರ ಸೆಕ್ಷನ್ 6(1)ರ ಅಡಿಯಲ್ಲಿ ಮಾಹಿತಿಗಾಗಿ ಅರ್ಜಿ - ",
        "salutation": "ಮಾನ್ಯರೇ,",
        "request_intro": "ಕೆಳಗೆ ಸಹಿ ಮಾಡಿದ ನಾನು, ಮಾಹಿತಿ ಹಕ್ಕು ಕಾಯ್ದೆ, 2005ರ ಸೆಕ್ಷನ್ 6(1)ರ ಅಡಿಯಲ್ಲಿ ಈ ಕೆಳಗಿನ ಮಾಹಿತಿಯನ್ನು ಕೋರುತ್ತೇನೆ:",
        "deadline_standard": "ದಯವಿಟ್ಟು {days} ದಿನಗಳೊಳಗೆ ಮಾಹಿತಿಯನ್ನು ಒದಗಿಸಿ (ಸೆಕ್ಷನ್ 7(1)).",
        "deadline_life": "ದಯವಿಟ್ಟು {hours} ಗಂಟೆಗಳೊಳಗೆ ಮಾಹಿತಿಯನ್ನು ಒದಗಿಸಿ (ಜೀವನ ಅಥವಾ ಸ್ವಾತಂತ್ರ್ಯಕ್ಕೆ ಸಂಬಂಧಿಸಿದ್ದು, ಸೆಕ್ಷನ್ 7(1) ನಿಬಂಧನೆ).",
        "fee_bpl": "ನಾನು ಬಡತನ ರೇಖೆಗಿಂತ ಕೆಳಗಿದ್ದೇನೆ (ಬಿಪಿಎಲ್) ಮತ್ತು ಸೆಕ್ಷನ್ 7(5)ರ ಅಡಿಯಲ್ಲಿ ಅರ್ಜಿ ಶುಲ್ಕದಿಂದ ವಿನಾಯಿತಿ ಹೊಂದಿದ್ದೇನೆ; ನನ್ನ ಬಿಪಿಎಲ್ ಪ್ರಮಾಣಪತ್ರವನ್ನು ಲಗತ್ತಿಸಲಾಗಿದೆ.",
        "fee_standard": "ನಿಗದಿತ ಅರ್ಜಿ ಶುಲ್ಕವನ್ನು ಅನ್ವಯವಾಗುವ ನಿಯಮಗಳ ಪ್ರಕಾರ ಪಾವತಿಸಲಾಗುತ್ತಿದೆ.",
        "exemption_note": "ನನಗೆ ತಿಳಿದಿರುವಂತೆ, ಕೋರಿದ ಮಾಹಿತಿಯು ಕಾಯ್ದೆಯ ಸೆಕ್ಷನ್ 8 ಮತ್ತು 9ರ ವಿನಾಯಿತಿಗಳ ವ್ಯಾಪ್ತಿಗೆ ಬರುವುದಿಲ್ಲ ಮತ್ತು ಇದು ನಿಮ್ಮ ಕಚೇರಿಗೆ ಸಂಬಂಧಿಸಿದೆ.",
        "context_prefix": "ಸಂದರ್ಭ (ಸ್ವಯಂಪ್ರೇರಿತವಾಗಿ ನೀಡಲಾಗಿದೆ; ಸೆಕ್ಷನ್ 6(2)ರ ಅಡಿಯಲ್ಲಿ ಕಾರಣ ಅಗತ್ಯವಿಲ್ಲ): ",
        "enclosures_prefix": "ಲಗತ್ತುಗಳು: ", "closing": "ತಮ್ಮ ವಿಶ್ವಾಸಿ,",
        "reference_label": "ಉಲ್ಲೇಖ ಸಂಖ್ಯೆ", "date_label": "ದಿನಾಂಕ",
    },
    "ml": {
        "to": "സേവനത്തിൽ,", "pio": "പബ്ലിക് ഇൻഫർമേഷൻ ഓഫീസർ,",
        "subject_prefix": "വിഷയം: വിവരാവകാശ നിയമം, 2005ലെ സെക്ഷൻ 6(1) പ്രകാരം വിവരത്തിനുള്ള അപേക്ഷ - ",
        "salutation": "ബഹുമാനപ്പെട്ട സർ/മാഡം,",
        "request_intro": "താഴെ ഒപ്പിടുന്ന ഞാൻ, വിവരാവകാശ നിയമം, 2005ലെ സെക്ഷൻ 6(1) പ്രകാരം താഴെപ്പറയുന്ന വിവരങ്ങൾ ആവശ്യപ്പെടുന്നു:",
        "deadline_standard": "ദയവായി {days} ദിവസത്തിനുള്ളിൽ വിവരം നൽകുക (സെക്ഷൻ 7(1)).",
        "deadline_life": "ദയവായി {hours} മണിക്കൂറിനുള്ളിൽ വിവരം നൽകുക (ജീവനോ സ്വാതന്ത്ര്യമോ സംബന്ധിച്ചത്, സെക്ഷൻ 7(1) വ്യവസ്ഥ).",
        "fee_bpl": "ഞാൻ ദാരിദ്ര്യരേഖയ്ക്ക് താഴെയുള്ള ആളാണ് (ബിപിഎൽ), സെക്ഷൻ 7(5) പ്രകാരം അപേക്ഷാ ഫീസിൽ നിന്ന് ഒഴിവാക്കപ്പെട്ടിരിക്കുന്നു; എന്റെ ബിപിഎൽ സർട്ടിഫിക്കറ്റിന്റെ പകർപ്പ് ഇതോടൊപ്പം ഉണ്ട്.",
        "fee_standard": "നിശ്ചിത അപേക്ഷാ ഫീസ് ബാധകമായ നിയമങ്ങൾ പ്രകാരം അടച്ചിട്ടുണ്ട്.",
        "exemption_note": "എനിക്കറിയാവുന്നിടത്തോളം, ആവശ്യപ്പെട്ട വിവരം നിയമത്തിലെ സെക്ഷൻ 8, 9 എന്നിവയിലെ ഒഴിവാക്കലുകളിൽ വരുന്നതല്ല, മാത്രമല്ല ഇത് നിങ്ങളുടെ ഓഫീസുമായി ബന്ധപ്പെട്ടതാണ്.",
        "context_prefix": "പശ്ചാത്തലം (സ്വമേധയാ നൽകിയത്; സെക്ഷൻ 6(2) പ്രകാരം കാരണം ആവശ്യമില്ല): ",
        "enclosures_prefix": "അനുബന്ധങ്ങൾ: ", "closing": "വിശ്വസ്തതയോടെ,",
        "reference_label": "റഫറൻസ് നമ്പർ", "date_label": "തീയതി",
    },
}


def generate_text(d: RtiDraft, reference: str, on: date, rules: RtiRules, *, fee_note: str | None = None) -> str:
    """Statutory-language draft. Wording follows the Act's Sections 6(1), 7(1), 7(5) and 8/9.

    The fixed template (headers, salutation, deadline/fee/exemption sentences) is rendered in
    ``d.language`` from ``RTI_TEMPLATE_STRINGS`` above, falling back to English for a language not
    yet covered there. The applicant's own words - subject, questions, context, name, address -
    are inserted exactly as given, never translated.
    """
    t = RTI_TEMPLATE_STRINGS.get(d.language, RTI_TEMPLATE_STRINGS["en"])
    deadline_sentence = t["deadline_life"].format(hours=rules.life_liberty_hours) if d.life_or_liberty else t["deadline_standard"].format(days=rules.response_days)
    fee = fee_note or (t["fee_bpl"] if d.below_poverty_line else t["fee_standard"])
    qs = "\n".join(f"{i}. {q}" for i, q in enumerate(d.questions, start=1))
    parts = [
        f"{t['reference_label']}: {reference}", f"{t['date_label']}: {on.strftime('%d %B %Y')}", "",
        t["to"], t["pio"], d.public_authority, "",
        f"{t['subject_prefix']}{d.subject}", "",
        t["salutation"], "",
        t["request_intro"], "",
        qs, "",
    ]  # fmt: skip
    if d.purpose:
        parts += [f"{t['context_prefix']}{d.purpose.strip()}", ""]
    parts += [deadline_sentence, fee, t["exemption_note"]]
    if d.attachments:
        parts += ["", f"{t['enclosures_prefix']}" + "; ".join(d.attachments)]
    parts += ["", t["closing"], d.applicant_name, d.applicant_address]
    return "\n".join(parts)


def render_pdf(text: str, *, title: str, font_path: str | None = None) -> bytes:
    """Render draft text to PDF with reportlab.

    Non-Latin text requires a Unicode TrueType font (``font_path``); without one this
    raises ``NotConfigured`` instead of emitting garbled glyphs.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font = "Helvetica"
    if not text.isascii() and not all(ord(c) < 256 for c in text):
        if not font_path:
            raise NotConfigured("This RTI contains non-Latin text; configure a Unicode font (RTI_PDF_FONT) to export it as PDF.")
        pdfmetrics.registerFont(TTFont("CivicLensUnicode", font_path))
        font = "CivicLensUnicode"
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, pageCompression=0)
    c.setTitle(title)
    width, height = A4
    margin, size, leading = 56, 11, 15
    y = height - margin
    c.setFont(font, size)
    for raw_line in text.split("\n"):
        line, words = "", raw_line.split(" ")
        wrapped: list[str] = []
        for w in words:
            trial = f"{line} {w}".strip()
            if pdfmetrics.stringWidth(trial, font, size) > width - 2 * margin and line:
                wrapped.append(line)
                line = w
            else:
                line = trial
        wrapped.append(line)
        for ln in wrapped:
            if y < margin:
                c.showPage()
                c.setFont(font, size)
                y = height - margin
            c.drawString(margin, y, ln)
            y -= leading
    c.save()
    return buf.getvalue()


def countdown(app: RtiApplication, now: datetime) -> Countdown:
    if app.status in (RtiStatus.RESPONDED, RtiStatus.CLOSED):
        return Countdown("answered", None, None, app.due_at, app.deadline_is_estimate)
    if app.due_at is None:
        return Countdown("not_started", None, None, None, False)
    delta = app.due_at - now
    hours = delta.total_seconds() / 3600
    if delta < timedelta(0):
        return Countdown("overdue", -((-delta).days), hours, app.due_at, app.deadline_is_estimate)
    days = delta.days
    state = "due_today" if days == 0 else "running"
    return Countdown(state, days, hours, app.due_at, app.deadline_is_estimate)


def due_reminders(app: RtiApplication, now: datetime, rules: RtiRules) -> list[int]:
    """Reminder thresholds (days-left) newly reached and not yet sent. Idempotent."""
    if app.status is not RtiStatus.FILED or app.due_at is None:
        return []
    days_left = (app.due_at - now).days if app.due_at >= now else -1
    return sorted((t for t in rules.reminder_days if 0 <= days_left <= t and t not in app.reminders_sent), reverse=True)[:1]


class RtiRepository(Protocol):
    def add(self, app: RtiApplication) -> None: ...
    def get(self, app_id: str) -> RtiApplication | None: ...
    def update(self, app: RtiApplication) -> None: ...
    def list_for_owner(self, owner_id: str) -> list[RtiApplication]: ...
    def list_filed(self) -> list[RtiApplication]: ...


class RtiService:
    def __init__(self, repo: RtiRepository, rules: RtiRules | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self._repo, self.rules = repo, rules or RtiRules()
        self._clock = clock or (lambda: datetime.now(UTC))

    def _owned(self, ctx: AuthContext, app_id: str) -> RtiApplication:
        require(ctx, Permission.RTI_MANAGE_OWN)
        app = self._repo.get(app_id)
        if app is None or app.owner_id != ctx.user_id:
            raise NotFound("RTI application not found.")  # same answer for "not yours"
        return app

    def create(self, ctx: AuthContext, draft: RtiDraft) -> RtiApplication:
        require(ctx, Permission.RTI_MANAGE_OWN)
        app = RtiApplication(str(uuid.uuid4()), ctx.user_id, validate_draft(draft), created_at=self._clock())
        self._repo.add(app)
        return app

    def update_draft(self, ctx: AuthContext, app_id: str, draft: RtiDraft) -> RtiApplication:
        app = self._owned(ctx, app_id)
        if app.status not in (RtiStatus.DRAFT, RtiStatus.GENERATED):
            raise ValidationFailed("A filed RTI can no longer be edited.")
        app.draft, app.status, app.generated_text = validate_draft(draft), RtiStatus.DRAFT, None
        self._repo.update(app)
        return app

    def generate(self, ctx: AuthContext, app_id: str, *, fee_note: str | None = None) -> RtiApplication:
        app = self._owned(ctx, app_id)
        if app.status not in (RtiStatus.DRAFT, RtiStatus.GENERATED):
            raise ValidationFailed("This RTI has already been filed.")
        now = self._clock()
        display_date = now.astimezone(DISPLAY_TZ).date()  # the citizen's own calendar day, not the UTC storage clock's
        app.reference = app.reference or generate_reference("RTI", display_date)
        app.generated_text = generate_text(app.draft, app.reference, display_date, self.rules, fee_note=fee_note)
        app.status = RtiStatus.GENERATED
        self._repo.update(app)
        return app

    def mark_filed(self, ctx: AuthContext, app_id: str, *, received_at: datetime | None = None) -> RtiApplication:
        app = self._owned(ctx, app_id)
        if app.status is not RtiStatus.GENERATED:
            raise ValidationFailed("Generate the RTI before marking it as filed.")
        now = self._clock()
        if received_at and received_at > now:
            raise ValidationFailed("Receipt date cannot be in the future.", details={"field": "received_at"})
        app.filed_at, app.received_at = now, received_at or now
        app.deadline_is_estimate = received_at is None
        app.due_at = self.rules.deadline(app.received_at, life_or_liberty=app.draft.life_or_liberty)
        app.status = RtiStatus.FILED
        self._repo.update(app)
        return app

    def mark_responded(self, ctx: AuthContext, app_id: str) -> RtiApplication:
        app = self._owned(ctx, app_id)
        if app.status is not RtiStatus.FILED:
            raise ValidationFailed("Only a filed RTI can be marked as answered.")
        app.status = RtiStatus.RESPONDED
        self._repo.update(app)
        return app

    def track(self, ctx: AuthContext, app_id: str) -> tuple[RtiApplication, Countdown]:
        app = self._owned(ctx, app_id)
        return app, countdown(app, self._clock())

    def export_pdf(self, ctx: AuthContext, app_id: str, *, font_path: str | None = None) -> bytes:
        app = self._owned(ctx, app_id)
        if not app.generated_text or not app.reference:
            raise ValidationFailed("Generate the RTI before exporting it.")
        return render_pdf(app.generated_text, title=f"RTI {app.reference}", font_path=font_path)

