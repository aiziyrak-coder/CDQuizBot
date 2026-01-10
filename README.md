# CDQuizBot - Test Yaratish va Yechish Telegram Boti

Professional Telegram boti testlar yaratish, yechish va natijalarni kuzatish uchun.

## 🚀 Xususiyatlar

- ✅ **Testlar yaratish** - Word (.docx) yoki PDF formatida testlar yaratish (BEPUL)
- ✅ **Testlarni yechish** - Aralash javoblar bilan professional test interfeysi
- ✅ **Balans va to'lov tizimi** - To'lov tizimi bilan testlarni yechish
- ✅ **Admin tomonidan to'lov tasdiqlash** - Adminlar to'lovlarni tasdiqlash
- ✅ **Yetakchilar jadvali** - Test natijalarini solishtirish
- ✅ **Natijalarni saqlash** - Barcha natijalarni saqlash va ko'rsatish
- ✅ **Davom ettirish/Restart** - Yarim qolgan testlarni davom ettirish yoki qayta boshlash
- ✅ **Random javoblar** - Har safar test boshlanganda javoblar aralash tartibda

## 📋 Talablar

- Python 3.8+ (3.11+ tavsiya etiladi)
- pip (Python package manager)

## 🔧 O'rnatish

1. **Repository'ni klonlash:**
```bash
git clone https://github.com/aiziyrak-coder/CDQuizBot.git
cd CDQuizBot
```

2. **Virtual environment yaratish (tavsiya etiladi):**
```bash
python -m venv venv
# Windows uchun:
venv\Scripts\activate
# Linux/Mac uchun:
source venv/bin/activate
```

3. **Zaruriy paketlarni o'rnatish:**
```bash
pip install -r requirements.txt
```

4. **Bot konfiguratsiyasini sozlash:**

`bot.py` faylida quyidagi parametrlarni o'zgartiring:

```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # @BotFather dan olingan token
ADMIN_GROUP_ID = -5143660617  # Adminlar guruhi ID
ADMIN_IDS = [5573250102, 6417011612]  # Admin Telegram ID'lari
CARD_NUMBER = "5614 6887 1938 3324"  # To'lov kartasi raqami
TEST_TAKING_COST = 10000.0  # Test yechish narxi (so'm)
```

5. **Botni ishga tushirish:**
```bash
python bot.py
```

## 📝 Test Fayl Format

Test fayli quyidagi formatda bo'lishi kerak:

```
++++
1. Nechinchi yilda federal hukumat...?
====
#1950 va 1960-yillarda
====
1960 yilda
====
1974 yilda
====
1975 yilda
++++
2. Ikkinchi savol matni?
====
#To'g'ri javob
====
Noto'g'ri javob 1
====
Noto'g'ri javob 2
====
Noto'g'ri javob 3
```

### Format Qoidalari:

- `++++` - Yangi testni boshlaydi (bir nechta test bo'lishi mumkin, ular bitta test sifatida birlashtiriladi)
- `1.`, `2.`, `3.` - Savollar tartib raqami bilan (raqam. savol matni)
- `====` - Har bir javobdan oldin separator
- `#` - To'g'ri javob oldiga `#` belgisi qo'yiladi
- Har bir savolda kamida 2 ta javob bo'lishi kerak
- Har bir savolda faqat bitta to'g'ri javob bo'lishi kerak

## 🎮 Foydalanish

### Foydalanuvchi uchun:

1. `/start` - Botni ishga tushirish
2. **📝 Test yaratish** - Test nomini kiriting va Word/PDF fayl yuklang
3. **📋 Testlar ro'yxati** - Mavjud testlarni ko'rish va tanlash
4. **💳 Balansni to'ldirish** - Summa tanlang, to'lov qiling va chek yuboring
5. **💰 Hisobim** - Balans, yaratilgan va yechilgan testlar statistikasi

### Test Yechish:

1. Test tanlang yoki link orqali kirish
2. Agar balans yetarli bo'lsa, avtomatik to'lov qilinadi
3. Har bir savolga javob bering yoki o'tkazib yuboring
4. Har bir javobdan keyin darhol feedback ko'rasiz
5. Test tugagach, natijalarni va yetakchilar jadvalidagi o'rningizni ko'rasiz

## 🛠️ Texnik Ma'lumotlar

### Texnologiyalar:

- **Framework**: python-telegram-bot 20.7+
- **Database**: SQLite (async) - SQLAlchemy ORM
- **File parsing**: python-docx, pypdf
- **Async**: asyncio, aiosqlite

### Database Strukturasi:

- `users` - Foydalanuvchilar ma'lumotlari va balans
- `tests` - Testlar
- `questions` - Savollar
- `answers` - Javoblar
- `test_results` - Test natijalari
- `user_answers` - Foydalanuvchi javoblari
- `payments` - To'lovlar
- `test_access` - Testga kirish huquqlari

## 📁 Fayl Strukturasi

```
CDQuizBot/
├── bot.py              # Asosiy bot kodlari
├── database.py         # Database modellari va sozlash
├── file_parser.py      # Test fayllarini pars qilish
├── requirements.txt    # Python paketlari
├── README.md          # Ushbu fayl
├── .gitignore         # Git ignore qilinadigan fayllar
├── bot.db             # SQLite database (avtomatik yaratiladi)
├── test_files/        # Yuklangan test fayllari
└── payment_screenshots/ # To'lov cheklari (adminlar uchun)
```

## 🔐 Xavfsizlik

- Bot tokenini va admin ma'lumotlarini xavfsiz saqlang
- `.gitignore` fayli keraksiz fayllarni GitHub'ga yuklamaydi
- To'lov kartasi raqamini o'zgartirishni unutmang

## 🤝 Hissa Qo'shish

Pull request'lar qabul qilinadi! Iltimos, katta o'zgarishlar uchun avval issue oching.

## 📄 Litsenziya

Bu loyiha ochiq kodli dastur sifatida taqdim etilgan.

## 📞 Aloqa

Muammolar yoki takliflar uchun [Issues](https://github.com/aiziyrak-coder/CDQuizBot/issues) bo'limidan foydalaning.

---

⭐ Agar sizga foydali bo'lsa, repository'ni yulduzcha bilan belgilang!
