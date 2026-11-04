# انتقال یک‌باره خروجی‌های تصویری و ویدئویی به GitHub

فایل‌های متنی پروژه در PR شماره ۱ بارگذاری شده‌اند؛ فایل‌های باینری اصلی (تصاویر PNG، ویدئوهای MP4 و نمودارها) در ZIP کامل پروژه قرار دارند. **تا وقتی این مراحل اجرا نشود، انتقال همه فایل‌ها به GitHub کامل نیست.**

۱. بسته `GazeBloom_full_project_2026-11-04.zip` را از گفتگو دانلود و در یک پوشه استخراج کنید.

۲. شاخه پژوهشی را clone کنید:

```bash
git clone --branch import/research-foundation-v1 https://github.com/ehsanrs2/GazeBloom.git
cd GazeBloom
```

۳. با جایگزین‌کردن مسیر واقعی پوشه استخراج‌شده، فقط خروجی‌های تاریخی را کپی و بررسی کنید:

```bash
cp -a /path/to/unpacked/GazeBloom/outputs/gaussian_lca_v0 ./outputs/
cp -a /path/to/unpacked/GazeBloom/outputs/waveoptics_q1_v1 ./outputs/
sha256sum -c outputs/ARCHIVE_SHA256SUMS.txt
```

۴. پس از PASS تمام checksumها:

```bash
git add outputs/gaussian_lca_v0 outputs/waveoptics_q1_v1
git commit -m "Archive original GazeBloom pilot media and Q1 plots"
git push origin import/research-foundation-v1
```

۵. GitHub Actions در PR را بررسی و در صورت رضایت merge کنید.

نکات: فایل‌های ویدئویی/تصویری داده تجربی چشم انسان نیستند. تولید دوباره ممکن است checksum باینری متفاوت بدهد. `outputs/reproduction/` در gitignore است و خروجی اجرای مجدد محسوب می‌شود.
