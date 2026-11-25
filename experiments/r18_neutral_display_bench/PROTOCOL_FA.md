# R18 — کیت اندازه‌گیری مستقل نور نمایشگر (بدون انسان)

## هدف
در R17 زمان STOP در metadata اعلام می‌شد. R18 هر دو لبه (marker الکتریکی خارجی و نور فتودیود) را از یک فایل دوکاناله استخراج می‌کند. در نتیجه هر دو لبه بازه نمونه‌برداری دارند. این آزمایش از H1 جداست؛ هیچ تصویر پژوهشی، داده انسانی یا دوربین ندارد.

## تجهیزات پیشنهادی، نه تجهیزات تأییدشده موجود
- مانیتور و رایانه لینوکس، Python دارای Tk.
- فتودیود با تقویت‌کننده/مدار خوانش مناسب و اسیلوسکوپ یا DAQ دوکاناله با ثبت هم‌زمان و امکان خروجی CSV. از پروب و سطوح ولتاژ سازگار با تجهیزات و اتصال ایمن استفاده شود؛ هیچ اتصال مستقیم به برق شهر یا داخل مانیتور لازم نیست.
- منبع تحریک خارجی که همان رخداد هم marker الکتریکی پایدار (CH1) ایجاد کند و هم فرمان Esc به رایانه برساند (مثلاً ابزار آزمون USB HID با خروجی marker هم‌بسته). طراحی و تأیید این سخت‌افزار جزو این PR نیست. فشردن دستی Esc بدون marker مشترک، آزمون نوری معتبر R18 نیست.
- CH2 خروجی حسگر روی مرکز وصله خاکستری؛ جایگاه حسگر، روشنایی محیط، نوع پنل، تنظیمات refresh، روشنایی و پردازش تصویر ثابت و ثبت شوند. یک حسگر فقط نقطه خودش را اندازه می‌گیرد.

## اجرای bench
```bash
sudo apt install python3-tk
python3 experiments/r18_neutral_display_bench/bench_gui.py --operator-bench
```
وصله خاکستری خنثی و ثابت است. قبل از ARM تجهیزات را آماده کنید. ARM یک‌بار وصله را روشن‌تر می‌کند، Esc یا STOP آن را به خنثی برمی‌گرداند و restart ندارد. timeout نرم‌افزاری ۱۵ ثانیه صرفاً محافظ bench است و نباید به‌عنوان marker سخت‌افزاری تفسیر شود. آزمون‌های timeout، close و button بدون marker جداگانه معتبر نیستند. نه fullscreen، نه flicker خودکار، نه تصویر پژوهشی.

دو کانال را در **یک acquisition** ثبت کنید، حداقل ۱ ksample/s پیشنهاد اولیه برای bench (نه استاندارد ایمنی). حداقل ۱۰۰ms قبل و ۲۰۰ms بعد از marker پیشنهاد می‌شود. marker باید قبل از فرمان Esc ثبت شود یا هم‌زمانی و اختلاف زمانی آن مستقلاً بررسی شود. نرم‌افزار تنها فاصله marker خارجی تا نور محلی را می‌سنجد، شامل تأخیر مسیر HID/OS/GUI/پنل. این زمان برابر latency داخلی Tk یا زمان واکنش انسان نیست.

CSV استانداردشده (واحد زمان ms، دامنه سیگنال به واحد ثبت دستگاه):
```text
timestamp_ms,trigger_signal,photodiode_signal
```
CSV خام دستگاه را محلی حفظ کنید؛ برای تبدیل واحد و ستون‌ها از یک کپی استفاده کرده و روش تبدیل و هش هر دو را ثبت کنید. اختلاف clock/skew کانال، پاسخ زمانی سنسور و عدم‌قطعیت trigger باید مستقل بررسی شوند. داده‌های real bench در `local_sessions/` نگهداری شوند.

```bash
mkdir -p experiments/r18_neutral_display_bench/local_sessions
cp experiments/r18_neutral_display_bench/metadata_TEMPLATE.json experiments/r18_neutral_display_bench/local_sessions/meta.json
# trace.csv را در همین دایرکتوری قرار دهید و هش آن را در meta.json ثبت کنید
sha256sum experiments/r18_neutral_display_bench/local_sessions/trace.csv
# مقادیر low/high/active/neutral را از ثبت مرجع واقعی وارد کنید؛ فقط پس از تأیید clock مشترک true
python3 experiments/r18_neutral_display_bench/two_channel.py \
  --metadata experiments/r18_neutral_display_bench/local_sessions/meta.json \
  --trace experiments/r18_neutral_display_bench/local_sessions/trace.csv \
  --out experiments/r18_neutral_display_bench/local_sessions/report.json
```
خروجی فقط بازه گسسته اختلاف دو لبه است: [light_previous - trigger_next, light_next - trigger_previous]. نمونه‌برداری بیش از ۲ms فاصله، نبود marker یکتا و پایدار، نبود baseline، عبور هم‌زمان/مبهم، بازگشت نور یا بیش از ۱۰٪ overshoot و کمتر از ۵۰ms مشاهده خنثی بعد از crossing، نتیجه قابل قبول تولید نمی‌کند. قواعد ۲ms/۵۰ms/۱۰٪ حدود قراردادی مهندسی اولیه‌اند، نه حدود بالینی. فاصله بین نمونه‌ها و خطای کالیبراسیون/اسکن فیزیکی هنوز جداگانه باید بررسی شوند.

## شواهد مورد انتظار
پیشنهاد اولیه: ۲۰ capture مستقل در مرکز (یک capture برای هر اجرای bench) و سپس در صورت امکان بالا و پایین پنل. همه captureها، حتی شکست‌ها، نگهداری شوند. نتایج را به تفکیک موقعیت، refresh و حالت مانیتور گزارش کنید، نه فقط بهترین نمونه. هیچ داده مصنوعی به‌عنوان داده واقعی بازنام‌گذاری نشود.

CI فقط تست داده ساختگی و تغییر رنگ widget در Xvfb را انجام می‌دهد؛ هیچ نور، دستگاه یا داوطلب واقعی اندازه‌گیری نمی‌شود. تا وقتی تجهیزات، marker و داده واقعی فراهم نشده‌اند، وضعیت `BENCH_KIT_IMPLEMENTED__PHYSICAL_EVIDENCE_PENDING` است. گیت‌های R15/H1 مستقل و باز هستند.
