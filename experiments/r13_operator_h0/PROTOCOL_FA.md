# GazeBloom / R13 — اجرای H0 روی مانیتور واقعی، بدون الزام تجهیزات، قبل از پایلوت انسانی

**تاریخ: ۱۰ نوامبر ۲۰۲۶**  
**وضعیت: ابزار نرم‌افزاری برای مرور محلی + رفع نقص تخصیص تصاویر، نه آزمایش انسانی**  
**ورود به H1: منوط به بررسی جداگانه ایمنی، رضایت، الزامات محلی و تصمیم صریح مسئول پژوهش**

## وضعیت ادغام و پیش‌نیاز شاخه

در زمان شروع R13، بررسی زنده GitHub نشان داد برخلاف گزارش ادغام کاربر، **PR #16 هنوز OPEN است و main روی PR #15 قرار دارد**. بنابراین R13 از آخرین Commit شاخه R12 ساخته شده و باید **فعلاً PR آن به شاخه R12 هدف بگیرد**. بعد از ادغام واقعی PR #16، base PR جدید را با main هماهنگ کنیم؛ از نسبت‌دادن کد R12 به main تا آن زمان خودداری شود.

## مسئله پژوهش و تصمیم

R12 چهار زوج تصویر واژه‌ای با کنتراست فرضی نزدیک ۳٫۱۸:۱ تولید کرد؛ این اعداد از مدل sRGB استخراج شدند، نه از اندازه‌گیری مانیتور. تصاویر در GitHub Actions هش و بررسی عددی شده‌اند اما بازبینی روی **نمایشگر واقعی محل مطالعه** هنوز **۰/۲۵** بود. R13 نرم‌افزاری فراهم می‌کند که اپراتور بتواند تصاویر را به‌صورت **تک‌فریم، فقط با کنترل دستی و با برچسب تأییدنشده** روی همان مانیتور ببیند و چک‌لیست محلیِ متصل به SHA-256 را تهیه کند.

این مرحله **تجهیزات تخصصی، موبایل یا داوطلب لازم ندارد**. داشتن نمایشگر و توان بررسی بصری توسط مسئول مطالعه برای H0 کافی است؛ سنجش طیف، luminance واقعی یا دیوپتر تطابق همچنان بررسی‌های جداگانه و اختیاری هستند.

## بخش ۱ — آماده‌سازی و بررسی شخص اپراتور

نیازها: Python و وابستگی‌های \`uv --extra research\` (NumPy/Pillow)، و برای GUI بسته Tk سیستم. کد هیچ ارتباط شبکه، ضبط ویدئو، فلاش، انیمیشن، زمان‌بندی نمایش یا آزمایش مشارکت‌کننده ندارد.

### قدم‌های پیشنهادی در رایانه شخصی

~~~bash
# داخل مخزن GazeBloom در شاخه پژوهشی R13
uv sync --locked --extra research

# ایجاد ۸ PNG ثابت R12 در یک پوشه محلی خالی
uv run --locked --extra research \
  python experiments/r12_display_review/generate_candidates.py \
  --out experiments/r13_operator_h0/local_sessions/r12_candidates

# ایجاد پرونده بررسیِ کاملاً PENDING، متصل به هش همان فایل‌ها
uv run --locked --extra research \
  python experiments/r13_operator_h0/workflow.py prepare-review \
  --candidates experiments/r13_operator_h0/local_sessions/r12_candidates \
  --out experiments/r13_operator_h0/local_sessions/review

# فقط اپراتور، در محیط بدون حضور آزمودنی: نمایش تک‌تصویر و مرور دستی
uv run --locked --extra research \
  python experiments/r13_operator_h0/workflow.py inspect-operator \
  --candidates experiments/r13_operator_h0/local_sessions/r12_candidates \
  --operator-only

# پس از بررسی واقعی و ویرایش محلی review_PENDING.json:
uv run --locked --extra research \
  python experiments/r12_display_review/review_gate.py \
  --candidates experiments/r13_operator_h0/local_sessions/r12_candidates \
  --review experiments/r13_operator_h0/local_sessions/review/review_PENDING.json
~~~

خروجی مرورگر یک پنجره با برچسب برجسته **OPERATOR ONLY / NO PARTICIPANTS**، تصویر PNG ثابت ۶۴۰×۳۶۰ و دکمه‌های Previous/Next/Close است. بدون پخش خودکار، بدون fullscreen اجباری و بدون کنترل دوربین؛ تغییر فقط پس از کلیک اپراتور رخ می‌دهد. حتی اجرای این پنجره **به‌تنهایی review را PASS نمی‌کند** و نرم‌افزار چیزی از شرایط واقعی مانیتور تشخیص نمی‌دهد.

فایل‌های نام/حریم خصوصی و review محلی باید در \`local_sessions/\` بمانند (gitignored). برای هر چهار واژه **خوانایی واقعی، لبه‌های رنگی، ناراحتی، الگو، روشنایی معمول، نور محیط، HDR/Night Light و وضعیت ICC** ثبت شود. اندازه‌گیری \`cd/m²\` بدون نورسنج و \`SPD\` بدون طیف‌سنج ممنوع است.

### نقاط توقف

- تصاویر R12 برای **بازبینی اپراتور** هستند، نه نمایش برای مشارکت‌کننده. اپراتور در صورت مشاهده ناراحتی، الگوی نامطلوب یا چشم‌زدگی، همان لحظه پنجره را ببندد و مورد را FAIL ثبت کند.
- تصاویر اگرچه ایستا و غیرچشمک‌زن‌اند، **گواهی ایمنی برای همه افراد ندارند**. به‌ویژه سابقه حساسیت به الگو و تشنج نوری نیاز به احتیاط دارد.
- \`review_gate.py\` حتی در صورت ۲۵/۲۵ بررسی مثبت، صرفاً \`ADMINISTRATIVE_REVIEW_COMPLETE__SEPARATE_AUTHORIZATION_REQUIRED\` می‌دهد و \`human_exposure_authorized = false\` می‌ماند.
- بدون تصمیم حقوقی/اخلاقی مناسب محل اجرا، اطلاع‌رسانی و رضایت متناسب، حریم خصوصی و تأییدِ صریحِ فایل‌ها و روش نمایش، **هیچ داوطلبی دعوت و هیچ H1 اجرا نمی‌شود**.
- دوربین گوشی اختیاری است و در R13 **اصلاً روشن یا استفاده نمی‌شود**.

## بخش ۲ — اصلاح مهم R10: هر چهار تصویر در هر دو شرط

نسخه R10 یک برنامه هشت‌نوبتی X/Y با چهار تکرار از هر شرط داشت، اما **به‌طور صریح واژهٔ همان نوبت را مشخص نمی‌کرد**. اگر اپراتور واژه‌ها را دلخواه تخصیص دهد، تفاوت سختی واژه/آشنایی می‌تواند با تفاوت X و Y اشتباه شود.

R13 یک **binding بدون نمایش** می‌سازد که در آن:

- چهار واژه \`NOVA\`، \`LUMA\`، \`MIRA\` و \`TORA\` به‌صورت تعیین‌پذیر از یک seed محلی، در چهار جفت جایگاه T01/T05، T02/T06، T03/T07 و T04/T08 اختصاص پیدا می‌کنند؛
- همان واژه دقیقاً یک‌بار در شرط X و یک‌بار در شرط Y قرار می‌گیرد، با فاصله **چهار نوبت**؛
- برنامه X/Y از R10 بدون تغییر باقی می‌ماند و هر دو حالت وارونه‌اش معتبرند؛
- هر ردیف مسیر نسبی تصویر و SHA-256 واقعی PNG، مدت پیشنهاد‌شده مشاهده و استراحت را دارد؛
- هیچ داده انسانی، تصویر جدید، پاسخ، خودکارسازی نمایش یا مجوز مشارکت‌کننده تولید نمی‌شود.

### تولید mapping صرفاً جهت برنامه‌ریزی

~~~bash
# تولید برنامه R10 برای یک کد آزمایشی غیرواقعی، فقط برای بررسی فنی
uv run --locked python experiments/r10_human_feasibility/pilot.py plan \
  --participant-code P000 --seed local-dry-run-private-seed \
  --out experiments/r13_operator_h0/local_sessions/r10_dummy

uv run --locked --extra research \
  python experiments/r13_operator_h0/workflow.py bind \
  --candidates experiments/r13_operator_h0/local_sessions/r12_candidates \
  --plan experiments/r13_operator_h0/local_sessions/r10_dummy/trials.csv \
  --plan-manifest experiments/r13_operator_h0/local_sessions/r10_dummy/manifest.json \
  --seed local-binding-seed-never-publish \
  --out experiments/r13_operator_h0/local_sessions/binding_dummy
~~~

خروجی \`trial_image_binding_NOT_APPROVED.csv\` و \`binding_manifest_NOT_APPROVED.json\` است. با تغییر seed خصوصی یا کد مستعار، ترتیب واژه‌ها تغییر می‌کند. این برنامه **ادعای کورسازی موفق، تصادفی‌سازی کامل آزمایش بالینی یا کاهش همه سوگیری‌ها ندارد**؛ واژه‌ها در فاصله چهار نوبت تکرار می‌شوند و خودِ رنگ ممکن است قابل شناسایی باشد. استفاده از seed در فرمان CLI ممکن است در history سیستم ثبت شود؛ در آزمایش واقعی آن را در فایل خصوصی/محیط محدود اجرا کرده و به مخزن نفرستید.

## بخش ۳ — داده‌های H1 و مسائل اخلاقی

**R13 به مطالعه H1 اجازه اجرا نمی‌دهد**، اما پس از بازبینی و تصویب جداگانه می‌توان برنامه R10 را برای سنجش تجربیِ گزارش‌شدهٔ وضوح/راحتی و خوانایی استفاده کرد؛ برنامه فعلی برای تمرین روی تصاویر ایستا و *feasibility* است، نه تأیید مکانیسم Chromatic Aberration. تغییر pupil/iris در گوشی، حتی اگر ثبت شود، تخمین مستقیم تطابق دیوپتری نیست.

برای مثال، اگر محل اجرای پروژه فنلاند باشد، <https://tenk.fi/en/ethical-review/ethical-review-human-sciences> برخی طراحی‌ها مانند مواجهه با محرک‌های بسیار قوی یا مخاطرات ایمنی را نیازمند بررسی پیشینی می‌داند. **این سند فرض نمی‌کند محل آزمایش فنلاند است**؛ مقررات و نیاز بررسیِ واقعی باید برای محل/نهاد پژوهش تعیین شود. در صورت لزوم، تأیید اخلاقی پیش از ورود مشارکت‌کننده اخذ شود؛ پس از شروع داده‌گیری ممکن است قابل‌صدور نباشد.

هیچ فایل رضایت امضاشده، ویدئوی چشم، نام، ایمیل، شماره سریال دستگاه، کد واقعی شرکت‌کننده یا اطلاعات حساس نباید در GitHub Actions، Pull Request یا artifact عمومی ثبت شود.

## بخش ۴ — معیار تصمیم پایان R13

**PASS مهندسی** فقط زمانی که آزمون‌های مستقل UI-independent و سناریوهای خطا PASS شوند: رد فایل تغییرکرده، pin صحیح SHA-256، عدم overwrite، خروجی all-PENDING، برنامه هشت‌نوبتی با دو شرط برای هر واژه و منع camera/human exposure.

**هنوز باز و نه PASS:** مشاهدهٔ اپراتور روی مانیتور کاربر، ۲۵ چک‌لیست R12، بازبینی اخلاقی/ایمنی واقعی، تأیید فایل‌های دقیق و حق توقف. هیچ کد CI نمی‌تواند اینها را ادعای موفق اعلام کند.

**نخستین گام بعدی با مسئول اجرا:** استفاده از ابزار مرور در سیستم خود، ثبت نتیجه واقعی و وضعیت هریک از چهار جفت؛ در صورت مناسب بودن از نظر ایمنی و موافقت با پژوهش انسانی، طراحی مستقل اجرای H1 به جای تکرار آزمایش‌های صرفاً مدل‌سازی.

## منابع

- Finnish National Board on Research Integrity (TENK), [ethical review in human sciences](https://tenk.fi/en/ethical-review/ethical-review-human-sciences), example for applicable jurisdictions only.
- [WCAG 2.2 large-text contrast](https://www.w3.org/TR/WCAG22/#contrast-minimum), design reference, not photic safety certification.
- [Epilepsy Foundation photosensitive seizures and visual patterns](https://www.epilepsy.com/what-is-epilepsy/seizure-triggers/photosensitivity).
- [R10 consent and safety](../r10_human_feasibility/CONSENT_AND_SAFETY_FA.md), [R12 image audit](../r12_display_review/PREFLIGHT_RESULTS_FA.md).
