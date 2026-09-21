// CivicLens - Multilingual Citizen Rights Handbook & Application Guide (7 Indian Languages)

export const CITIZEN_GUIDES_MULTILINGUAL = {
  en: [
    {
      id: 'rti_mastery',
      title: 'How to File an Effective RTI (Right to Information 2005)',
      icon: '🏛️',
      summary: 'The RTI Act 2005 is one of India\'s most potent transparency instruments. Learn how to draft bulletproof applications.',
      steps: [
        {
          step: 1,
          title: 'Identify the Public Authority & PIO',
          desc: 'Direct your application to the Public Information Officer (PIO) or Assistant PIO of the specific department (e.g., BBMP, Bescom, DJB).'
        },
        {
          step: 2,
          title: 'Draft Point-Wise Specific Questions',
          desc: 'Ask for certified copies of documents, inspection of works, tender agreements, measurement books, or daily progress logs. Avoid asking for opinions or "why" questions.'
        },
        {
          step: 3,
          title: 'Enclose Statutory Fee (₹10)',
          desc: 'Pay ₹10 via Court Fee Stamp, Demand Draft, Indian Postal Order (IPO), or online payment on RTI portal. (BPL cardholders are 100% fee-exempt).'
        },
        {
          step: 4,
          title: 'Mandatory 30-Day Response Timeframe',
          desc: 'The PIO is legally bound under Section 7(1) to reply within 30 days (48 hours if it concerns life or liberty). If unanswered, information must be provided free of cost!'
        },
        {
          step: 5,
          title: 'First Appeal if Denied',
          desc: 'If no reply arrives within 30 days or info is misleading, file a First Appeal under Section 19(1) to the designated First Appellate Authority (FAA) at zero fee.'
        }
      ],
      proTip: 'CivicLens RTI Generator automatically formats your letter with mandatory legal clauses and statutory time limits.'
    },
    {
      id: 'fir_rights',
      title: 'Your Rights When Filing an FIR (BNSS 173 / CrPC 154)',
      icon: '🚨',
      summary: 'Understanding cognizable offences, the Zero FIR doctrine, and what to do if police refuse registration.',
      steps: [
        {
          step: 1,
          title: 'Cognizable vs Non-Cognizable Offences',
          desc: 'For cognizable offences (theft, physical assault, cyber fraud, cheating > ₹20k), police MUST register an FIR immediately without judicial permission.'
        },
        {
          step: 2,
          title: 'The Mandatory "Zero FIR" Doctrine',
          desc: 'A Zero FIR can be registered at ANY police station across India, regardless of where the crime took place. The station will record the crime and transfer it to the local station.'
        },
        {
          step: 3,
          title: 'Right to Free Copy & Reading',
          desc: 'You have a statutory right to have the FIR read over to you before signing, and to receive an immediate free certified physical copy.'
        },
        {
          step: 4,
          title: 'If Police Refuse Registration',
          desc: 'Send the complaint in writing by Registered Post to the Superintendent of Police (SP) or Commissioner under Section 175(3) BNSS / 154(3) CrPC, or file a private complaint before the Magistrate under Section 175(3) / 156(3).'
        }
      ],
      proTip: 'You can also file cyber financial frauds instantly at helpline 1930 or cybercrime.gov.in within the first 2 golden hours.'
    },
    {
      id: 'consumer_rights',
      title: 'Filing Consumer Cases Without a Lawyer (E-Daakhil)',
      icon: '🛒',
      summary: 'The Consumer Protection Act 2019 allows any consumer to seek compensation for defective goods and deficient services without hiring an advocate.',
      steps: [
        {
          step: 1,
          title: 'Issue 15-Day Written Legal Notice',
          desc: 'Notify the company/seller via email or registered post demanding refund or defect correction within 15 days.'
        },
        {
          step: 2,
          title: 'Register on E-Daakhil (edaakhil.nic.in)',
          desc: 'Create an account on the national consumer dispute portal. Upload your invoice, proof of payment, and email correspondence.'
        },
        {
          step: 3,
          title: 'Pecuniary Jurisdiction & Zero Fees',
          desc: 'Filing is 100% FREE for claims up to ₹5 Lakhs! District Commissions handle claims up to ₹50 Lakhs.'
        },
        {
          step: 4,
          title: 'Direct Video Conferencing Hearings',
          desc: 'You can attend virtual hearings from your smartphone without visiting physical courtrooms.'
        }
      ],
      proTip: 'Keep digital screenshots and courier delivery slips intact; they serve as primary admissible evidence under the Consumer Protection Act.'
    },
    {
      id: 'municipal_escalation',
      title: 'Civic Grievance Escalation Ladder',
      icon: '🏢',
      summary: 'How to escalate unaddressed potholes, garbage dumps, or water outages to the highest civic authorities.',
      steps: [
        {
          step: 1,
          title: 'Level 1: Ward Level Complaint',
          desc: 'File with Assistant Executive Engineer (AEE) / Junior Engineer via municipal app or CivicLens (1 to 7 days SLA).'
        },
        {
          step: 2,
          title: 'Level 2: Zonal Executive Engineer',
          desc: 'If unaddressed after 7 days, tag the complaint reference ID and submit grievance to Zonal Office.'
        },
        {
          step: 3,
          title: 'Level 3: Central Grievance Portal (CPGRAMS / State Portal)',
          desc: 'Escalate to Chief Commissioner or Prime Minister/Chief Minister grievance cell (e.g. pgportal.gov.in, Seva Sindhu, Aaple Sarkar).'
        },
        {
          step: 4,
          title: 'Level 4: Lokayukta / State Human Rights Commission',
          desc: 'For gross negligence causing injury (e.g. death/injury due to open pothole/manhole), file petition before State Lokayukta.'
        }
      ],
      proTip: 'CivicLens Grievance Tracker triggers an auto-escalation alert on Day 30 to help you file an RTI or First Appeal.'
    }
  ],

  hi: [
    {
      id: 'rti_mastery',
      title: 'आरटीआई (सूचना का अधिकार अधिनियम 2005) कैसे दाखिल करें',
      icon: '🏛️',
      summary: 'आरटीआई अधिनियम 2005 नागरिकों का सबसे शक्तिशाली हथियार है। जानें कि अचूक आवेदन कैसे लिखें।',
      steps: [
        {
          step: 1,
          title: 'लोक सूचना अधिकारी (PIO) की पहचान करें',
          desc: 'संबंधित विभाग के लोक सूचना अधिकारी (PIO) या सहायक पीआईओ के नाम आवेदन पत्र संबोधित करें।'
        },
        {
          step: 2,
          title: 'बिंदुवार स्पष्ट प्रश्न पूछें',
          desc: 'दस्तावेजों की प्रमाणित प्रतियां, कार्य निरीक्षण, टेंडर अनुबंध, कार्य पुस्तिका और दैनिक प्रगति रिपोर्ट मांगें। "क्यों" वाले प्रश्न पूछने से बचें।'
        },
        {
          step: 3,
          title: '₹10 का वैधानिक शुल्क संलग्न करें',
          desc: 'कोर्ट फीस स्टाम्प, पोस्टल ऑर्डर (IPO), डिमांड ड्राफ्ट या ऑनलाइन पोर्टल से ₹10 शुल्क दें। (बीपीएल कार्डधारक पूरी तरह निःशुल्क हैं)।'
        },
        {
          step: 4,
          title: '30 दिनों के भीतर जवाब की समय-सीमा',
          desc: 'धारा 7(1) के तहत अधिकारी को 30 दिनों में जानकारी देना अनिवार्य है (जीवन व स्वतंत्रता से जुड़े मामलों में 48 घंटे)। 30 दिन बाद जानकारी मुफ्त दी जाएगी।'
        },
        {
          step: 5,
          title: 'जवाब न मिलने पर प्रथम अपील (First Appeal)',
          desc: '30 दिनों में जवाब न मिलने पर धारा 19(1) के तहत प्रथम अपीलीय प्राधिकारी (FAA) को बिना किसी शुल्क के अपील दाखिल करें।'
        }
      ],
      proTip: 'सिविक लेंस आरटीआई जनरेटर आपके आवेदन में सभी कानूनी धाराओं को स्वतः जोड़ देता है।'
    },
    {
      id: 'fir_rights',
      title: 'एफआईआर दर्ज कराते समय आपके कानूनी अधिकार (BNSS 173 / CrPC 154)',
      icon: '🚨',
      summary: 'संज्ञेय अपराध, जीरो एफआईआर का नियम और पुलिस द्वारा मना करने पर क्या करें।',
      steps: [
        {
          step: 1,
          title: 'संज्ञेय व असंज्ञेय अपराध समझें',
          desc: 'संज्ञेय अपराध (चोरी, मारपीट, धोखाधड़ी, साइबर अपराध) में पुलिस को तुरंत एफआईआर दर्ज करना अनिवार्य है।'
        },
        {
          step: 2,
          title: 'जीरो एफआईआर (Zero FIR) का नियम',
          desc: 'घटना कहीं भी हुई हो, भारत के किसी भी पुलिस थाने में जीरो एफआईआर दर्ज कराई जा सकती है।'
        },
        {
          step: 3,
          title: 'निःशुल्क प्रमाणित प्रति पाने का अधिकार',
          desc: 'एफआईआर पर हस्ताक्षर से पूर्व उसे पढ़कर सुनाना और तुरंत उसकी निशुल्क प्रमाणित कॉपी देना पुलिस का कानूनी कर्तव्य है।'
        },
        {
          step: 4,
          title: 'यदि पुलिस एफआईआर दर्ज न करे',
          desc: 'धारा 175(3) BNSS के तहत पुलिस अधीक्षक (SP) या कमिश्नर को रजिस्टर्ड डाक से शिकायत भेजें या मजिस्ट्रेट के समक्ष निजी परिवाद दाखिल करें।'
        }
      ],
      proTip: 'साइबर वित्तीय फ्रॉड होने पर पहले 2 घंटों में तुरंत 1930 डायल करें या cybercrime.gov.in पर रिपोर्ट करें।'
    },
    {
      id: 'consumer_rights',
      title: 'बिना वकील के उपभोक्ता कोर्ट में केस दाखिल करना (ई-दाखिल)',
      icon: '🛒',
      summary: 'उपभोक्ता संरक्षण अधिनियम 2019 के तहत खराब सामान व सेवाओं के खिलाफ कोई भी नागरिक घर बैठे ऑनलाइन केस दर्ज कर सकता है।',
      steps: [
        {
          step: 1,
          title: '15 दिनों का कानूनी नोटिस भेजें',
          desc: 'कंपनी को ईमेल या डाक द्वारा 15 दिनों में रिफंड या खराबी ठीक करने का नोटिस दें।'
        },
        {
          step: 2,
          title: 'ई-दाखिल (edaakhil.nic.in) पर रजिस्टर करें',
          desc: 'उपभोक्ता विवाद पोर्टल पर बिल, भुगतान रसीद और ईमेल पत्राचार अपलोड करें।'
        },
        {
          step: 3,
          title: '₹5 लाख तक के दावों पर शून्य शुल्क',
          desc: '₹5 लाख तक के मामलों में कोर्ट फीस शून्य है। जिला उपभोक्ता आयोग ₹50 लाख तक के मामले सुनता है।'
        },
        {
          step: 4,
          title: 'वीडियो कॉन्फ्रेंसिंग से ऑनलाइन सुनवाई',
          desc: 'आप बिना अदालत जाए अपने फोन से वीडियो कॉल द्वारा सुनवाई में शामिल हो सकते हैं।'
        }
      ],
      proTip: 'खरीद के स्क्रीनशॉट और इनवॉइस हमेशा सुरक्षित रखें, यह कोर्ट में प्राथमिक साक्ष्य बनते हैं।'
    },
    {
      id: 'municipal_escalation',
      title: 'नागरिक समस्याओं की समाधान सीढ़ी (Escalation Ladder)',
      icon: '🏢',
      summary: 'सड़क के गड्ढे, कचरा व जलभराव की शिकायत उच्च अधिकारियों तक कैसे पहुंचाएं।',
      steps: [
        {
          step: 1,
          title: 'स्तर 1: वार्ड स्तर की शिकायत',
          desc: 'सिविक लेंस या नगर निगम ऐप से वार्ड इंजीनियर को शिकायत दर्ज करें (समय सीमा: 1 से 7 दिन)।'
        },
        {
          step: 2,
          title: 'स्तर 2: जोनल अधिशासी अभियंता (Executive Engineer)',
          desc: '7 दिन में समाधान न होने पर जोनल कार्यालय को शिकायत संख्या देकर अग्रेषित करें।'
        },
        {
          step: 3,
          title: 'स्तर 3: केंद्रीय जन शिकायत पोर्टल (CPGRAMS / राज्य पोर्टल)',
          desc: 'मुख्यमंत्री/प्रधानमंत्री शिकायत पोर्टल (pgportal.gov.in) पर सीधे शिकायत दर्ज करें।'
        },
        {
          step: 4,
          title: 'स्तर 4: लोकायुक्त / मानवाधिकार आयोग',
          desc: 'खुले गड्ढे या लापरवाही से चोट लगने पर राज्य लोकायुक्त में याचिका दाखिल करें।'
        }
      ],
      proTip: 'सिविक लेंस ट्रैकर 30वें दिन स्वतः आरटीआई अपील का विकल्प सक्रिय कर देता है।'
    }
  ],

  kn: [
    {
      id: 'rti_mastery',
      title: 'ಮಾಹಿತಿ ಹಕ್ಕು (RTI 2005) ಅರ್ಜಿ ಸಲ್ಲಿಸುವುದು ಹೇಗೆ',
      icon: '🏛️',
      summary: 'RTI ಕಾಯ್ದೆ 2005 ಭಾರತೀಯ ನಾಗರಿಕರ ಪ್ರಬಲ ಅಸ್ತ್ರವಾಗಿದೆ. ಪರಿಣಾಮಕಾರಿ ಅರ್ಜಿ ಬರೆಯುವುದನ್ನು ಕಲಿಯಿರಿ.',
      steps: [
        {
          step: 1,
          title: 'ಸಾರ್ವಜನಿಕ ಮಾಹಿತಿ ಅಧಿಕಾರಿಯನ್ನು (PIO) ಗುರುತಿಸಿ',
          desc: 'ಸಂಬಂಧಿತ ಇಲಾಖೆಯ (BBMP, Bescom, BWSSB) ಮಾಹಿತಿ ಅಧಿಕಾರಿಗೆ ಅರ್ಜಿಯನ್ನು ಸಲ್ಲಿಸಿ.'
        },
        {
          step: 2,
          title: 'ನಿರ್ದಿಷ್ಟ ಪ್ರಶ್ನೆಗಳನ್ನು ಪಟ್ಟಿ ಮಾಡಿ',
          desc: 'ದಾಖಲೆಗಳ ದೃಢೀಕೃತ ಪ್ರತಿಗಳು, ಕಾಮಗಾರಿ ತಪಾಸಣೆ, ಟೆಂಡರ್ ಒಪ್ಪಂದಗಳು ಮತ್ತು ಪ್ರಗತಿ ವರದಿಗಳನ್ನು ಕೇಳಿ.'
        },
        {
          step: 3,
          title: '₹10 ಶುಲ್ಕ ಪಾವತಿಸಿ',
          desc: 'ಕೋರ್ಟ್ ಫೀ ಸ್ಟ್ಯಾಂಪ್, ಪೋಸ್ಟಲ್ ಆರ್ಡರ್ ಅಥವಾ ಆನ್‌ಲೈನ್ ಪೋರ್ಟಲ್ ಮೂಲಕ ₹10 ಶುಲ್ಕ ನೀಡಿ (BPL ಕಾರ್ಡ್‌ದಾರರಿಗೆ ಉಚಿತ).'
        },
        {
          step: 4,
          title: '30 ದಿನಗಳ ಕಾಲಮಿತಿ',
          desc: 'ಸೆಕ್ಷನ್ 7(1)ರ ಪ್ರಕಾರ 30 ದಿನಗಳಲ್ಲಿ ಮಾಹಿತಿ ನೀಡುವುದು ಕಡ್ಡಾಯ. ಇಲ್ಲದಿದ್ದರೆ ಉಚಿತವಾಗಿ ಮಾಹಿತಿ ನೀಡಬೇಕು.'
        },
        {
          step: 5,
          title: 'ಪ್ರಥಮ ಮೇಲ್ಮನವಿ (First Appeal)',
          desc: '30 ದಿನಗಳಲ್ಲಿ ಉತ್ತರ ಬಾರದಿದ್ದರೆ ಪ್ರಥಮ ಮೇಲ್ಮನವಿ ಪ್ರಾಧಿಕಾರಕ್ಕೆ (FAA) ಉಚಿತವಾಗಿ ಮೇಲ್ಮನವಿ ಸಲ್ಲಿಸಿ.'
        }
      ],
      proTip: 'ಸಿವಿಕ್ ಲೆನ್ಸ್ RTI ಜನರೇಟರ್ ನಿಮ್ಮ ಅರ್ಜಿಯನ್ನು ಕಾನೂನುಬದ್ಧ ನಿಯಮಗಳೊಂದಿಗೆ ಸಿದ್ಧಪಡಿಸುತ್ತದೆ.'
    },
    {
      id: 'fir_rights',
      title: 'ಎಫ್‌ಐಆರ್ (FIR) ದಾಖಲಿಸುವಾಗ ನಿಮ್ಮ ಕಾನೂನು ಹಕ್ಕುಗಳು',
      icon: '🚨',
      summary: 'ಗಂಭೀರ ಅಪರಾಧಗಳು, ಝೀರೋ ಎಫ್‌ಐಆರ್ ನಿಯಮ ಮತ್ತು ಪೊಲೀಸರು ನಿರಾಕರಿಸಿದಾಗ ಏನು ಮಾಡಬೇಕು.',
      steps: [
        {
          step: 1,
          title: 'ಕಾಗ್ನಿಜೇಬಲ್ ಅಪರಾಧಗಳು',
          desc: 'ಕಳ್ಳತನ, ಹಲ್ಲೆ, ಸೈಬರ್ ವಂಚನೆ ಮುಂತಾದ ಅಪರಾಧಗಳಿಗೆ ಪೊಲೀಸರು ತಕ್ಷಣ ಎಫ್‌ಐಆರ್ ದಾಖಲಿಸಬೇಕು.'
        },
        {
          step: 2,
          title: 'ಝೀರೋ ಎಫ್‌ಐಆರ್ (Zero FIR) ನಿಯಮ',
          desc: 'ಘಟನೆ ಎಲ್ಲಿಯೇ ನಡೆದಿದ್ದರೂ ಭಾರತದ ಯಾವುದೇ ಪೊಲೀಸ್ ಠಾಣೆಯಲ್ಲಿ ಝೀರೋ ಎಫ್‌ಐಆರ್ ದಾಖಲಿಸಬಹುದು.'
        },
        {
          step: 3,
          title: 'ಉಚಿತ ಪ್ರತಿಯನ್ನು ಪಡೆಯುವ ಹಕ್ಕು',
          desc: 'ಸಹಿ ಮಾಡುವ ಮೊದಲು ಎಫ್‌ಐಆರ್ ಓದಿ ಕೇಳುವ ಮತ್ತು ಉಚಿತ ದೃಢೀಕೃತ ಪ್ರತಿಯನ್ನು ಪಡೆಯುವ ಹಕ್ಕಿದೆ.'
        },
        {
          step: 4,
          title: 'ಪೊಲೀಸರು ನಿರಾಕರಿಸಿದರೆ',
          desc: 'ಜಿಲ್ಲಾ ಪೊಲೀಸ್ ವರಿಷ್ಠಾಧಿಕಾರಿ (SP) ಅಥವಾ ಕಮಿಷನರ್‌ಗೆ ರಿಜಿಸ್ಟರ್ಡ್ ಪೋಸ್ಟ್ ಮೂಲಕ ದೂರು ಕಳುಹಿಸಿ.'
        }
      ],
      proTip: 'ಸೈಬರ್ ಆರ್ಥಿಕ ವಂಚನೆ ನಡೆದಾಗ ಮೊದಲ 2 ಗಂಟೆಗಳಲ್ಲಿ 1930 ಗೆ ಕರೆ ಮಾಡಿ.'
    },
    {
      id: 'consumer_rights',
      title: 'ವಕೀಲರಿಲ್ಲದೆ ಗ್ರಾಹಕರ ನ್ಯಾಯಾಲಯದಲ್ಲಿ ದೂರು (E-Daakhil)',
      icon: '🛒',
      summary: 'ದೋಷಪೂರಿತ ವಸ್ತು ಅಥವಾ ಸೇವೆಗಳಿಗೆ ಪರಿಹಾರ ಪಡೆಯಲು ಇ-ದಾಖಿಲ್ ಮೂಲಕ ಆನ್‌ಲೈನ್ ಅರ್ಜಿ ಸಲ್ಲಿಸಿ.',
      steps: [
        {
          step: 1,
          title: '15 ದಿನಗಳ ನೋಟಿಸ್ ನೀಡಿ',
          desc: 'ಕಂಪನಿಗೆ ಇಮೇಲ್ ಮೂಲಕ ಹಣ ಮರುಪಾವತಿಗೆ 15 ದಿನಗಳ ಗಡುವು ನೀಡಿ.'
        },
        {
          step: 2,
          title: 'edaakhil.nic.in ನಲ್ಲಿ ನೋಂದಾಯಿಸಿ',
          desc: 'ಖಾತೆ ತೆರೆದು ಬಿಲ್ ಮತ್ತು ಇಮೇಲ್ ದಾಖಲೆಗಳನ್ನು ಅಪ್‌ಲೋಡ್ ಮಾಡಿ.'
        },
        {
          step: 3,
          title: '₹5 ಲಕ್ಷದವರೆಗೆ ಯಾವುದೇ ಕೋರ್ಟ್ ಫೀ ಇಲ್ಲ',
          desc: '₹5 ಲಕ್ಷದವರೆಗಿನ ದೂರುಗಳಿಗೆ ಶುಲ್ಕ ಶೂನ್ಯವಾಗಿರುತ್ತದೆ.'
        },
        {
          step: 4,
          title: 'ವಿಡಿಯೋ ಕಾನ್ಫರೆನ್ಸಿಂಗ್ ವಿಚಾರಣೆ',
          desc: 'ಮೊಬೈಲ್ ಫೋನ್ ಮೂಲಕವೇ ನೇರವಾಗಿ ವರ್ಚುವಲ್ ವಿಚಾರಣೆಗೆ ಹಾಜರಾಗಬಹುದು.'
        }
      ],
      proTip: 'ಖರೀದಿಯ ಸ್ಕ್ರೀನ್‌ಶಾಟ್ ಮತ್ತು ಇನ್‌ವಾಯ್ಸ್ ದಾಖಲೆಗಳನ್ನು ಸುರಕ್ಷಿತವಾಗಿಡಿ.'
    },
    {
      id: 'municipal_escalation',
      title: 'ನಾಗರಿಕ ಸಮಸ್ಯೆಗಳ ಹಂತ ಹಂತದ ಪರಿಹಾರ ಮಾರ್ಗ',
      icon: '🏢',
      summary: 'ರಸ್ತೆ ಗುಂಡಿ, ಕಸ ಮತ್ತು ಒಳಚರಂಡಿ ಸಮಸ್ಯೆಗಳನ್ನು ಹಿರಿಯ ಅಧಿಕಾರಿಗಳಿಗೆ ಮುಟ್ಟಿಸುವ ವಿಧಾನ.',
      steps: [
        {
          step: 1,
          title: 'ಹಂತ 1: ವಾರ್ಡ್ ಮಟ್ಟದ ದೂರು',
          desc: 'ಸಿವಿಕ್ ಲೆನ್ಸ್ ಮೂಲಕ ವಾರ್ಡ್ ಎಂಜಿನಿಯರ್‌ಗೆ ದೂರು ನೀಡಿ (1 ರಿಂದ 7 ದಿನಗಳ ಕಾಲಾವಕಾಶ).'
        },
        {
          step: 2,
          title: 'ಹಂತ 2: ವಲಯ ಕಾರ್ಯನಿರ್ವಾಹಕ ಎಂಜಿನಿಯರ್',
          desc: '7 ದಿನಗಳಲ್ಲಿ ಪರಿಹಾರವಾಗದಿದ್ದರೆ ವಲಯ ಕಚೇರಿಗೆ ಮೇಲ್ಮನವಿ ಸಲ್ಲಿಸಿ.'
        },
        {
          step: 3,
          title: 'ಹಂತ 3: ಮುಖ್ಯಮಂತ್ರಿ / ಕೇಂದ್ರ ಪರಿಹಾರ ಪೋರ್ಟಲ್',
          desc: 'ಸೇವಾ ಸಿಂಧು ಅಥವಾ pgportal.gov.in ನಲ್ಲಿ ನೇರ ದೂರು ದಾಖಲಿಸಿ.'
        },
        {
          step: 4,
          title: 'ಹಂತ 4: ಲೋಕಾಯುಕ್ತ / ಮಾನವ ಹಕ್ಕುಗಳ ಆಯೋಗ',
          desc: 'ನಿರ್ಲಕ್ಷ್ಯದಿಂದ ಪ್ರಾಣಹಾನಿ ಅಥವಾ ಗಾಯವಾದರೆ ಲೋಕಾಯುಕ್ತಕ್ಕೆ ಅರ್ಜಿ ಸಲ್ಲಿಸಿ.'
        }
      ],
      proTip: 'ಸಿವಿಕ್ ಲೆನ್ಸ್ ಟ್ರ್ಯಾಕರ್ 30ನೇ ದಿನ ಸ್ವಯಂಚಾಲಿತ RTI ಎಚ್ಚರಿಕೆಯನ್ನು ನೀಡುತ್ತದೆ.'
    }
  ]
};

// Return guides for requested language (fallback to English)
export const getCitizenGuides = (langCode = 'en') => {
  return CITIZEN_GUIDES_MULTILINGUAL[langCode] || CITIZEN_GUIDES_MULTILINGUAL.en;
};

export const CITIZEN_GUIDES = CITIZEN_GUIDES_MULTILINGUAL.en;

export const FREQUENTLY_ASKED_QUESTIONS_MULTILINGUAL = {
  en: [
    {
      q: 'Does CivicLens store my personal identity on public servers?',
      a: 'No. Your personal profile (name, phone, address) is stored strictly on your local device storage and injected directly into legal templates when you generate complaints.'
    },
    {
      q: 'Can I submit complaints directly to government portals?',
      a: 'CivicLens generates 100% legally compliant formal drafts, RTI requests, and provides direct links to CPGRAMS, state portals, and official nodal officer emails.'
    },
    {
      q: 'How accurate is the Case Outcome Prediction AI?',
      a: 'Predictions are calibrated against real Indian court precedents (Supreme Court, High Courts, Consumer Commissions) combined with statutory weights. It is intended for citizen legal awareness and guidance.'
    },
    {
      q: 'What languages does CivicLens support?',
      a: 'CivicLens supports 7 Indian languages for UI and drafting: English, Hindi (हिन्दी), Kannada (ಕನ್ನಡ), Tamil (தமிழ்), Telugu (తెలుగు), Marathi (मराठी), and Bengali (বাংলা).'
    }
  ],
  hi: [
    {
      q: 'क्या सिविक लेंस मेरी निजी जानकारी सार्वजनिक सर्वर पर स्टोर करता है?',
      a: 'नहीं। आपकी जानकारी (नाम, फोन, पता) केवल आपके फोन में सुरक्षित रहती है और पत्र बनाते समय सीधे ड्राफ्ट में जोड़ी जाती है।'
    },
    {
      q: 'क्या मैं सीधे सरकारी पोर्टल पर शिकायत भेज सकता हूँ?',
      a: 'सिविक लेंस कानूनी रूप से मान्य पत्र, आरटीआई आवेदन तैयार करता है और CPGRAMS व राज्य पोर्टलों के सीधे लिंक उपलब्ध कराता है।'
    },
    {
      q: 'केस परिणाम अनुमान कितना सटीक है?',
      a: 'यह सुप्रीम कोर्ट, हाई कोर्ट और उपभोक्ता आयोगों के वास्तविक ऐतिहासिक फैसलों पर आधारित है और कानूनी मार्गदर्शन प्रदान करता है।'
    },
    {
      q: 'सिविक लेंस किन भाषाओं का समर्थन करता है?',
      a: 'सिविक लेंस 7 भारतीय भाषाओं का समर्थन करता है: अंग्रेजी, हिन्दी, ಕನ್ನಡ, தமிழ், తెలుగు, मराठी और বাংলা।'
    }
  ],
  kn: [
    {
      q: 'ಸಿವಿಕ್ ಲೆನ್ಸ್ ನನ್ನ ವೈಯಕ್ತಿಕ ವಿವರಗಳನ್ನು ಸಾರ್ವಜನಿಕ ಸರ್ವರ್‌ನಲ್ಲಿ ಸಂಗ್ರಹಿಸುತ್ತದೆಯೇ?',
      a: 'ಇಲ್ಲ. ನಿಮ್ಮ ವಿವರಗಳು ನಿಮ್ಮ ಮೊಬೈಲ್‌ನಲ್ಲಿ ಮಾತ್ರ ಸುರಕ್ಷಿತವಾಗಿರುತ್ತವೆ ಮತ್ತು ದೂರು ಪತ್ರ ತಯಾರಿಸುವಾಗ ಮಾತ್ರ ಬಳಕೆಯಾಗುತ್ತವೆ.'
    },
    {
      q: 'ನಾನು ನೇರವಾಗಿ ಸರ್ಕಾರಿ ಪೋರ್ಟಲ್‌ಗಳಿಗೆ ದೂರು ಸಲ್ಲಿಸಬಹುದೇ?',
      a: 'ಸಿವಿಕ್ ಲೆನ್ಸ್ ಕಾನೂನುಬದ್ಧ ದೂರು ಮತ್ತು RTI ಪತ್ರಗಳನ್ನು ಸಿದ್ಧಪಡಿಸಿ, CPGRAMS ಮತ್ತು ರಾಜ್ಯ ಪೋರ್ಟಲ್‌ಗಳ ಲಿಂಕ್‌ಗಳನ್ನು ನೀಡುತ್ತದೆ.'
    },
    {
      q: 'ಕೇಸ್ ತೀರ್ಪಿನ ಅಂದಾಜು ಎಷ್ಟು ನಿಖರವಾಗಿದೆ?',
      a: 'ಸುಪ್ರೀಂ ಕೋರ್ಟ್ ಮತ್ತು ಹೈಕೋರ್ಟ್‌ನ ನೈಜ ತೀರ್ಪುಗಳ ಆಧಾರದ ಮೇಲೆ ಎಐ ಈ ಮಾರ್ಗದರ್ಶನ ನೀಡುತ್ತದೆ.'
    },
    {
      q: 'ಸಿವಿಕ್ ಲೆನ್ಸ್ ಯಾವ ಭಾಷೆಗಳನ್ನು ಬೆಂಬಲಿಸುತ್ತದೆ?',
      a: 'ಇಂಗ್ಲಿಷ್, ಹಿಂದಿ, ಕನ್ನಡ, ತಮಿಳು, ತೆಲುಗು, ಮರಾಠಿ ಮತ್ತು ಬಂಗಾಳಿ ಸೇರಿದಂತೆ 7 ಭಾರತೀಯ ಭಾಷೆಗಳನ್ನು ಬೆಂಬಲಿಸುತ್ತದೆ.'
    }
  ]
};

export const getFaqs = (langCode = 'en') => {
  return FREQUENTLY_ASKED_QUESTIONS_MULTILINGUAL[langCode] || FREQUENTLY_ASKED_QUESTIONS_MULTILINGUAL.en;
};

export const FREQUENTLY_ASKED_QUESTIONS = FREQUENTLY_ASKED_QUESTIONS_MULTILINGUAL.en;
