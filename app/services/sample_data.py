from app.models import (
    DischargeAnalysisResponse,
    PatientMetadata,
    MedicationInstruction,
    FollowUpTask,
    WarningSign,
)

SAMPLE_DISCHARGE_TEXT = """
ST. JUDE MEMORIAL HOSPITAL
SURGICAL DISCHARGE SUMMARY & INSTRUCTIONS
Record #SJM-84920
Discharge Date: October 24, 2024

PATIENT: Jenkins, Sarah | DOB: 04/12/1988 | MRN: #SJM-84920
ATTENDING SURGEON: Dr. Robert Chen, MD (Orthopedic Surgery)
ADMISSION DIAGNOSIS: Right Knee Medial Meniscus Tear (Complex)
OPERATIVE PROCEDURE: Right Knee Diagnostic and Operative Arthroscopy, Partial Medial Meniscectomy, Debridement
ANESTHESIA: General LMA with local femoral nerve block

HOSPITAL COURSE SUMMARY:
Patient tolerated procedure well without intraoperative complications. Stable in PACU. Vital signs within normal limits. Tolerating oral fluids and light diet. Voiding spontaneously. Ambulated 50 feet with crutches bearing weight as tolerated. Surgical dressing clean and intact. Discharged home in stable condition into the care of husband (Mark Jenkins).

POST-PROCEDURE HOME CARE INSTRUCTIONS:
1. ACTIVITY & WEIGHT-BEARING:
- Weight-bearing as tolerated (WBAT) with bilateral crutches for 7-10 days.
- Keep right leg elevated above heart level on pillows while resting to reduce edema. Do not place pillow directly under knee crease; keep knee in extended neutral position.
- Apply cryo cold therapy pack to right knee for 20 minutes every 2 hours while awake for the first 72 hours.
- Perform active ankle pump exercises (3 sets of 10 repetitions, 3 times daily) to promote venous return and prevent thromboembolism.

2. WOUND & DRESSING CARE:
- Waterproof surgical dressing must remain in place and kept clean and dry until follow-up suture inspection.
- Do not submerge operative knee in bath, hot tub, or pool. Brief showers permitted with waterproof sleeve covering.
- [Note: No dressing change required before clinic visit unless saturated; if drainage exceeds 50% of pad, contact clinic immediately].

3. MEDICATIONS PRESCRIBED:
- Cephalexin 500 MG Oral Capsule. Take 1 capsule by mouth every 6 hours for 7 days until complete. Finish entire course to prevent surgical site infection.
- Acetaminophen 500 MG Tablet. Take 1 to 2 tablets by mouth every 8 hours as needed for mild-to-moderate pain. Do not exceed 3,000 mg in 24 hours.
- Enoxaparin Sodium (Lovenox) 40 MG/0.4ML Syringe. Inject 0.4 mL subcutaneously into abdominal subcutaneous tissue once daily each morning for 10 days.

4. MANDATORY FOLLOW-UP APPOINTMENTS:
- Dr. Robert Chen, MD: Suture removal and Range-of-Motion evaluation on Thursday, Oct 31, 2024 at 10:30 AM at West Medical Pavilion, Suite 410.
- Physical Therapy Initial Clearance & Rehab Protocol: Monday, Nov 4, 2024 at 2:00 PM at St. Jude Rehabilitation Annex, Ground Floor.

5. RED-FLAG WARNING SIGNS (CONTACT SURGICAL CLINIC OR SEEK EMERGENCY CARE IMMEDIATELY):
- Oral temperature greater than 101.4°F (38.5°C) or persistent shaking chills.
- Sudden severe pain, tenderness, swelling, or localized warmth in right calf or lower extremity (Deep Vein Thrombosis red flags).
- Persistent soaking drainage, heavy bleeding, or foul odor emerging through knee dressing.
- Sudden shortness of breath, acute chest pain upon inspiration, or unexplained tachycardia (Pulmonary Embolism emergency - Call 911).

EMERGENCY / CLINIC CONTACT:
Orthopedic Triage Line: (555) 019-2834 | Emergency: 911
"""

def get_sample_discharge_data(lang: str = "en") -> DischargeAnalysisResponse:
    if lang == "hi":
        return DischargeAnalysisResponse(
            patient_info=PatientMetadata(
                patient_name="Sarah Jenkins",
                hospital_name="St. Jude Memorial Hospital",
                record_number="#SJM-84920",
                attending_physician="Dr. Robert Chen, MD",
                discharge_date="24 अक्टूबर, 2024",
                procedure_or_diagnosis="दाएं घुटने की आर्थ्रोस्कोपी (Right Knee Arthroscopy)"
            ),
            summary="सरल भाषा में: आपके दाहिने घुटने में फटी हुई कार्टिलेज को ठीक करने के लिए एक न्यूनतम चीरे वाली सर्जरी (आर्थ्रोस्कोपी) की गई है। आपका घुटना अच्छी तरह ठीक हो रहा है। इस सप्ताह आपके मुख्य लक्ष्य बर्फ और पैर को ऊंचा रखकर सूजन कम करना, दवाएं समय पर लेना, और सर्जरी की पट्टी को पूरी तरह सूखा और साफ रखना है।",
            recovery_milestones=[
                "हर 2 घंटे में 20 मिनट बर्फ लगाएं",
                "पैर को दिल के स्तर से ऊपर रखें",
                "पट्टी को पूरी तरह सूखा रखें"
            ],
            medication_instructions=[
                MedicationInstruction(
                    name="Cephalexin",
                    dosage="500mg",
                    route="Oral Capsule (मुंह से लेने वाला कैप्सूल)",
                    frequency="हर 6 घंटे में 1 कैप्सूल",
                    duration="7 दिन",
                    purpose="संक्रमण रोकने के लिए एंटीबायोटिक कोर्स",
                    verbatim_order="Cephalexin 500 MG Oral Capsule. Take 1 capsule by mouth every 6 hours for 7 days until complete. Finish entire course to prevent surgical site infection.",
                    patient_explanation="घुटने में संक्रमण से बचने के लिए एंटीबायोटिक। हर 6 घंटे में 1 गोली लें (नाश्ता, दोपहर का खाना, रात का खाना, सोने से पहले)। बेहतर महसूस होने पर भी दवा बीच में न छोड़ें।",
                    tips_or_warnings="पेट खराब होने पर भोजन या एक गिलास दूध के साथ लें।"
                ),
                MedicationInstruction(
                    name="Acetaminophen (Tylenol)",
                    dosage="500mg",
                    route="Oral Tablet (गोली)",
                    frequency="दर्द होने पर हर 8 घंटे में 1-2 गोली",
                    duration="आवश्यकतानुसार (PRN)",
                    purpose="दर्द निवारक (Pain Relief)",
                    verbatim_order="Acetaminophen 500 MG Tablet. Take 1 to 2 tablets by mouth every 8 hours as needed for pain. Max 3,000 mg in 24 hours.",
                    patient_explanation="दर्द निवारक। केवल दर्द होने पर लें। लिवर की सुरक्षा के लिए 24 घंटे में 6 से अधिक गोलियां कभी न लें।",
                    tips_or_warnings="पैरासिटामोल/एसिटामिनोफेन युक्त अन्य खांसी या दर्द की दवाओं के साथ न लें।"
                ),
                MedicationInstruction(
                    name="Enoxaparin (Lovenox)",
                    dosage="40mg / 0.4mL",
                    route="SubQ Syringe (पेट की त्वचा के नीचे इंजेक्शन)",
                    frequency="प्रतिदिन सुबह 1 बार",
                    duration="10 दिन",
                    purpose="रक्त के थक्के रोकने की दवा (Blood Thinner)",
                    verbatim_order="Enoxaparin Sodium 40 MG/0.4ML Syringe. Inject 0.4 mL subcutaneously once daily for 10 days.",
                    patient_explanation="घुटने की सर्जरी के बाद नसों में खतरनाक थक्के बनने से रोकने के लिए पेट में लगने वाला इंजेक्शन। हर सुबह एक ही समय पर लें।",
                    tips_or_warnings="इंजेक्शन वाली जगह पर हल्का नीला पड़ना सामान्य है।"
                )
            ],
            follow_up_tasks=[
                FollowUpTask(
                    id="task-1",
                    title="टांके निकालना और घुटने की जांच (Suture Removal)",
                    provider="Dr. Robert Chen, MD",
                    date_time="गुरुवार, 31 अक्टूबर • 10:30 AM",
                    location="वेस्ट मेडिकल पवेलियन, सुइट 410",
                    time_of_day="Morning",
                    completed=False,
                    type="appointment",
                    instructions="टांकों की जांच और लचीलेपन का परीक्षण।"
                ),
                FollowUpTask(
                    id="task-2",
                    title="फिजियोथेरेपी परामर्श (PT Clearance)",
                    provider="St. Jude Rehab Center",
                    date_time="सोमवार, 4 नवंबर • 2:00 PM",
                    location="रिहैबिलिटेशन एनेक्स, ग्राउंड फ्लोर",
                    time_of_day="Afternoon",
                    completed=False,
                    type="appointment",
                    instructions="पुनर्वास व्यायाम योजना शुरू करना।"
                ),
                FollowUpTask(
                    id="task-3",
                    title="टखने के व्यायाम (Ankle Pumps)",
                    provider="होम केयर गाइड",
                    date_time="प्रतिदिन 3 बार • 10-10 दोहराव",
                    location="घर पर",
                    time_of_day="Morning",
                    completed=True,
                    type="recovery_task",
                    instructions="पैरों के पंजों को ऊपर-नीचे हिलाएं ताकि रक्त संचार बना रहे।"
                )
            ],
            source_warning_signs=[
                WarningSign(
                    sign="101.4°F (38.5°C) से अधिक बुखार या तेज कंपकंपी",
                    severity="High Priority",
                    action="तुरंत सर्जन या क्लिनिक से संपर्क करें"
                ),
                WarningSign(
                    sign="दाहिनी पिंडली में अचानक तेज दर्द, लालिमा, या सूजन (DVT लक्षण)",
                    severity="Immediate ER",
                    action="तुरंत निकटतम आपातकालीन कक्ष (ER) जाएं"
                ),
                WarningSign(
                    sign="घुटने की पट्टी से लगातार रिसाव या दुर्गंध आना",
                    severity="Contact Surgeon",
                    action="सर्जन से संपर्क करें, पट्टी खुद न हटाएं"
                ),
                WarningSign(
                    sign="अचानक सांस फूलना या सांस लेते समय सीने में तेज दर्द",
                    severity="Call 911",
                    action="तुरंत 911 या आपातकालीन एम्बुलेंस को कॉल करें"
                )
            ],
            missing_or_ambiguous_information=[
                "डिस्चार्ज सारांश में पट्टी बदलने का सटीक दिन दर्ज नहीं है - कृपया आगामी फॉलो-अप में नर्स से स्पष्ट करें।"
            ],
            language="hi",
            is_synthetic_demo=True
        )

    elif lang == "bn":
        return DischargeAnalysisResponse(
            patient_info=PatientMetadata(
                patient_name="Sarah Jenkins",
                hospital_name="St. Jude Memorial Hospital",
                record_number="#SJM-84920",
                attending_physician="Dr. Robert Chen, MD",
                discharge_date="২৪ অক্টোবর, ২০২৪",
                procedure_or_diagnosis="ডান হাঁটুর আর্থ্রোস্কোপি (Right Knee Arthroscopy)"
            ),
            summary="সহজ বাংলায়: আপনার ডান হাঁটুর ছেঁড়া কার্টিলেজ সারানোর জন্য একটি ছোট ছিদ্রের অস্ত্রোপচার (আর্থ্রোস্কোপি) করা হয়েছে। আপনার হাঁটু দ্রুত সেরে উঠছে। এই সপ্তাহের মূল লক্ষ্য হলো বরফ ও পা উঁচুতে রেখে ফোলা কমানো, সময়মতো ওষুধ খাওয়া, এবং অস্ত্রোপচারের ব্যান্ডেজ সম্পূর্ণ শুকনো রাখা।",
            recovery_milestones=[
                "প্রতি ২ ঘণ্টায় ২০ মিনিট বরফ দিন",
                "হৃৎপিণ্ডের উচ্চতার চেয়ে পা উঁচুতে রাখুন",
                "ব্যান্ডেজ সম্পূর্ণ শুকনো রাখুন"
            ],
            medication_instructions=[
                MedicationInstruction(
                    name="Cephalexin",
                    dosage="500mg",
                    route="Oral Capsule (মুখে খাওয়ার ক্যাপসুল)",
                    frequency="প্রতি ৬ ঘণ্টায় ১টি ক্যাপসুল",
                    duration="৭ দিন",
                    purpose="সংক্রমণ প্রতিরোধক অ্যান্টিবায়োটিক",
                    verbatim_order="Cephalexin 500 MG Oral Capsule. Take 1 capsule by mouth every 6 hours for 7 days until complete. Finish entire course to prevent surgical site infection.",
                    patient_explanation="হাঁটুর ইনফেকশন রোধ করতে অ্যান্টিবায়োটিক। প্রতি ৬ ঘণ্টায় ১টি করে ক্যাপসুল খান (সকাল, দুপুর, রাত ও ঘুমানোর আগে)। সুস্থ বোধ করলেও পুরো কোর্স শেষ করুন।",
                    tips_or_warnings="পেটে সমস্যা হলে খাবারের সাথে বা এক গ্লাস দুধের সাথে খান।"
                ),
                MedicationInstruction(
                    name="Acetaminophen (Tylenol)",
                    dosage="500mg",
                    route="Oral Tablet (ট্যাবলেট)",
                    frequency="ব্যথা থাকলে প্রতি ৮ ঘণ্টায় ১-২টি",
                    duration="প্রয়োজনে (PRN)",
                    purpose="ব্যথানাশক (Pain Relief)",
                    verbatim_order="Acetaminophen 500 MG Tablet. Take 1 to 2 tablets by mouth every 8 hours as needed for pain. Max 3,000 mg in 24 hours.",
                    patient_explanation="ব্যথানাশক ওষুধ। তীব্র ব্যথা থাকলে খান। লিভারের সুরক্ষার জন্য দিনে ৬টির বেশি খাবেন না।",
                    tips_or_warnings="প্যারাসিটামলযুক্ত অন্য কোনো ঠান্ডা বা ব্যথার ওষুধের সাথে একযোগে খাবেন না।"
                ),
                MedicationInstruction(
                    name="Enoxaparin (Lovenox)",
                    dosage="40mg / 0.4mL",
                    route="SubQ Syringe (পেটের চামড়ার নিচে ইনজেকশন)",
                    frequency="প্রতিদিন সকালে ১ বার",
                    duration="১০ দিন",
                    purpose="রক্ত জমাট বাঁধা প্রতিরোধক (Blood Thinner)",
                    verbatim_order="Enoxaparin Sodium 40 MG/0.4ML Syringe. Inject 0.4 mL subcutaneously once daily for 10 days.",
                    patient_explanation="হাঁটুর অপারেশনের পর রক্ত জমাট বাঁধা রোধ করতে ইনজেকশন। প্রতিদিন সকালে একই সময়ে পেটের ত্বকের নিচে নিন।",
                    tips_or_warnings="ইনজেকশনের স্থানে হালকা দাগ বা কালশিটে স্বাভাবিক।"
                )
            ],
            follow_up_tasks=[
                FollowUpTask(
                    id="task-1",
                    title="সেলাই কাটা ও হাঁটু পরীক্ষা (Suture Removal)",
                    provider="Dr. Robert Chen, MD",
                    date_time="বৃহস্পতিবার, ৩১ অক্টোবর • ১০:৩০ AM",
                    location="ওয়েস্ট মেডিকেল প্যাভিলিয়ন, স্যুট ৪১০",
                    time_of_day="Morning",
                    completed=False,
                    type="appointment",
                    instructions="সেলাই অপসারণ এবং হাঁটু নাড়াচাড়ার সক্ষমতা পরীক্ষা।"
                ),
                FollowUpTask(
                    id="task-2",
                    title="ফিজিওথেরাপি পরামর্শ (PT Clearance)",
                    provider="St. Jude Rehab Center",
                    date_time="সোমবার, ৪ নভেম্বর • ২:০০ PM",
                    location="পুনর্বাসন কেন্দ্র, নিচতলা",
                    time_of_day="Afternoon",
                    completed=False,
                    type="appointment",
                    instructions="পুনরুদ্ধার ব্যায়াম পরিকল্পনা।"
                ),
                FollowUpTask(
                    id="task-3",
                    title="গোড়ালির ব্যায়াম (Ankle Pumps)",
                    provider="হোম কেয়ার গাইড",
                    date_time="প্রতিদিন ৩ বার • ১০টি করে",
                    location="বাসায়",
                    time_of_day="Morning",
                    completed=True,
                    type="recovery_task",
                    instructions="রক্ত সঞ্চালন সচল রাখতে গোড়ালি রিদমিকভাবে ওঠানামা করান।"
                )
            ],
            source_warning_signs=[
                WarningSign(
                    sign="১০১.৪° ফারেনহাইট (৩৮.৫° সে.)-এর বেশি জ্বর বা তীব্র কাঁপুনি",
                    severity="High Priority",
                    action="অবিলম্বে সার্জন বা ক্লিনিকে যোগাযোগ করুন"
                ),
                WarningSign(
                    sign="ডান পায়ের ডিমে হঠাৎ তীব্র ব্যথা, লালচে ভাব বা ফুলে যাওয়া (DVT লক্ষণ)",
                    severity="Immediate ER",
                    action="অবিলম্বে নিকটবর্তী ইমার্জেন্সি বিভাগে যান"
                ),
                WarningSign(
                    sign="হাঁটুর ব্যান্ডেজ ভিজে যাওয়া বা দুর্গন্ধযুক্ত স্রাব",
                    severity="Contact Surgeon",
                    action="সার্জনকে ফোন করুন, ব্যান্ডেজ নিজে খুলবেন না"
                ),
                WarningSign(
                    sign="হঠাৎ শ্বাসকষ্ট বা শ্বাস নেওয়ার সময় বুকে তীব্র ব্যথা",
                    severity="Call 911",
                    action="অবিলম্বে ৯১১ বা জরুরি অ্যাম্বুলেন্স ডাকুন"
                )
            ],
            missing_or_ambiguous_information=[
                "ব্যান্ডেজ খোলার কোনো নির্দিষ্ট সময় উল্লেখ নেই - ফলো-আপ ভিজিটে নার্সের সাথে যাচাই করুন।"
            ],
            language="bn",
            is_synthetic_demo=True
        )

    # Default: English
    return DischargeAnalysisResponse(
        patient_info=PatientMetadata(
            patient_name="Sarah Jenkins",
            hospital_name="St. Jude Memorial Hospital",
            record_number="#SJM-84920",
            attending_physician="Dr. Robert Chen, MD",
            discharge_date="Oct 24, 2024",
            procedure_or_diagnosis="R. Knee Arthroscopy (Partial Meniscectomy)"
        ),
        summary="You had a minimally invasive procedure to trim torn cartilage in your right knee. The joint is healing well. Your primary goals this week are keeping swelling down with ice and elevation, managing mild pain on a regular schedule, and keeping the surgical dressing completely clean and dry.",
        recovery_milestones=[
            "Ice 20 min / 2 hrs",
            "Elevate above heart",
            "Keep bandage dry"
        ],
        medication_instructions=[
            MedicationInstruction(
                name="Cephalexin",
                dosage="500mg",
                route="Oral Capsule",
                frequency="Every 6 hours",
                duration="7 days",
                purpose="Antibiotic Course to prevent surgical site infection",
                verbatim_order="Cephalexin 500 MG Oral Capsule. Take 1 capsule by mouth every 6 hours for 7 days until complete. Finish entire course to prevent surgical site infection.",
                patient_explanation="Antibiotic to prevent knee infection. Take 1 pill every 6 hours (suggested: Breakfast, Lunch, Dinner, Bedtime). Do not stop early even if you feel 100% better.",
                tips_or_warnings="Take with food or a glass of milk if stomach feels upset."
            ),
            MedicationInstruction(
                name="Acetaminophen (Tylenol)",
                dosage="500mg",
                route="Oral Tablet",
                frequency="Every 8 hours as needed",
                duration="As Needed (PRN)",
                purpose="Mild-to-moderate post-operative pain relief",
                verbatim_order="Acetaminophen 500 MG Tablet. Take 1 to 2 tablets by mouth every 8 hours as needed for pain. Max 3,000 mg in 24 hours.",
                patient_explanation="Pain reliever. Take when hurting, up to twice per 8 hours. Never take more than 6 pills in one day to safeguard your liver.",
                tips_or_warnings="Do not combine with other over-the-counter cold or pain medicines containing acetaminophen."
            ),
            MedicationInstruction(
                name="Enoxaparin (Lovenox)",
                dosage="40mg / 0.4mL",
                route="SubQ Syringe",
                frequency="Once daily each morning",
                duration="10 days",
                purpose="Blood thinner to prevent deep vein blood clots",
                verbatim_order="Enoxaparin Sodium 40 MG/0.4ML Syringe. Inject 0.4 mL subcutaneously once daily for 10 days.",
                patient_explanation="Blood thinner injection in the belly skin to prevent dangerous clots after knee surgery. Take at the same time each morning. Alternate left and right sides.",
                tips_or_warnings="Light bruising around the injection spot is normal and harmless."
            )
        ],
        follow_up_tasks=[
            FollowUpTask(
                id="task-1",
                title="Suture Removal & ROM Test",
                provider="Dr. Robert Chen • Orthopedic Clinic",
                date_time="Thursday, Oct 31 • 10:30 AM",
                location="Suite 410, West Medical Pavilion",
                time_of_day="Morning",
                completed=False,
                type="appointment",
                instructions="Dr. Chen will inspect the incision incisions and test gentle bending."
            ),
            FollowUpTask(
                id="task-2",
                title="Physical Therapy Clearance",
                provider="St. Jude PT & Sports Rehab Center",
                date_time="Monday, Nov 4 • 2:00 PM",
                location="Ground Floor, Rehabilitation Annex",
                time_of_day="Afternoon",
                completed=False,
                type="appointment",
                instructions="Initial evaluation and tailored home recovery exercise plan."
            ),
            FollowUpTask(
                id="task-3",
                title="Ankle Pump Exercises (3 sets x 10)",
                provider="Home Recovery Protocol",
                date_time="3 times daily",
                location="At home",
                time_of_day="Morning",
                completed=True,
                type="recovery_task",
                instructions="Point toes up and down rhythmically to prevent blood clots."
            ),
            FollowUpTask(
                id="task-4",
                title="Evening Wound Dressing Inspection",
                provider="Home Recovery Protocol",
                date_time="7:30 PM",
                location="At home",
                time_of_day="Evening",
                completed=False,
                type="recovery_task",
                instructions="Check waterproof dressing for excess fluid. Do not remove dressing."
            )
        ],
        source_warning_signs=[
            WarningSign(
                sign="Fever over 101.4°F (38.5°C) or persistent shaking chills",
                severity="High Priority",
                action="Contact surgeon or orthopedic clinic triage immediately"
            ),
            WarningSign(
                sign="Sudden severe calf pain, warmth, redness, or swelling in right lower leg (DVT signs)",
                severity="Immediate ER",
                action="Proceed to nearest emergency room immediately"
            ),
            WarningSign(
                sign="Persistent soaking drainage or foul odor through the knee bandages",
                severity="Contact Surgeon",
                action="Call surgeon's office. Do not attempt to re-dress or change dressing at home."
            ),
            WarningSign(
                sign="Shortness of breath or sharp chest pain upon breathing",
                severity="Call 911",
                action="Call 911 or emergency medical response immediately"
            )
        ],
        missing_or_ambiguous_information=[
            "No specific dressing change schedule was stated before the 7-day follow-up. Keep original waterproof dressing intact unless clinic advises otherwise."
        ],
        language="en",
        is_synthetic_demo=True
    )
