# ChromaBlur — Wave-optics Q1 & Measurement Q2 v1

این بسته در پاسخ به پرسش «چطور می‌توانیم بفهمیم تصویر روی مانیتور، اول الگوی مطلوب شبکیه را ایجاد می‌کند و دوم واقعاً تطابق چشم را تغییر می‌دهد؟» ایجاد شده است.

- `PROTOCOL_FA.md`: توضیح کامل مسئله، فرضیه‌ها، مراحل آزمون، محدودیت‌ها و ملاک تفسیر.
- `waveoptics_validation.py`: شبیه‌ساز اپتیکی ساده با PSF موجی و LCA و بهینه‌سازی تاری RGB.
- `psf_profiles.png`: نمودار PSF پیش‌بینی‌شده، هدف و شاهد.
- `predicted_retinal_images.png`: تصویر **محاسبه‌شده** روی شبکیه در مدل ثابت، نه ثبت واقعی.
- `metrics.csv`, `results.json`: خروجی عددی Q1.
- `analyze_accommodation.py`: برازش پاسخ تطابق به داده‌های **واقعی ثبت‌شده** در آینده؛ هنوز داده واقعی نداریم.
- `test_waveoptics.py`, `test_accommodation_analysis.py`: ۱۲ تست نرم‌افزاری و عددی.

از پوشه حاضر اجرا کنید:

```bash
python waveoptics_validation.py --out .
python -m unittest -v test_waveoptics test_accommodation_analysis
```

نتیجه فعلی: بهبود حدود ۱٫۳۵٪ / ۱٫۴۹٪ نسبت به شاهد ساده در Q1؛ **برای تأیید Q1 کافی نیست؛ Q2 هنوز بررسی نشده است.** این یک طراحی/شبیه‌سازی تحقیقاتی است، نه اثبات اثربخشی و نه ابزار درمانی.