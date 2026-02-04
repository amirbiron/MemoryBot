# 🧠 Memory Agent Bot

סוכן AI אישי לניהול זיכרון פתרונות קוד.

## מה זה?

בוט טלגרם שמאפשר לך לשמור פתרונות, טיפים וקוד, ולחפש אותם בשפה טבעית.
במקום לחפש בהיסטוריה של צ'אטים או בהערות ישנות - פשוט שואלים את הסוכן.

## ✨ יכולות

- **➕ שמירת פתרונות** - שמירה עם אישור מוקדם
- **🔎 חיפוש סמנטי** - "איך פתרנו את בעיית ה-caching?"
- **📚 רשימת זיכרונות** - צפייה בזיכרונות אחרונים
- **🏷️ חיפוש לפי תגית** - סינון לפי קטגוריות
- **📊 סטטיסטיקות** - נתונים על הזיכרונות
- **🗑️ מחיקת זיכרונות** - ניהול מלא

## 🛠 טכנולוגיות

- **Python** + FastAPI
- **python-telegram-bot** (Webhook)
- **MongoDB Atlas** + Vector Search
- **OpenAI Embeddings** (`text-embedding-3-small`)
- **Render** (פריסה)

## 🚀 התקנה

### 1. דרישות מוקדמות

- חשבון [MongoDB Atlas](https://www.mongodb.com/atlas) (חינמי)
- מפתח [OpenAI API](https://platform.openai.com/)
- בוט טלגרם (מ-[@BotFather](https://t.me/BotFather))
- חשבון [Render](https://render.com/) (חינמי)

### 2. הגדרת MongoDB Atlas

#### 2.1 יצירת Cluster
1. צור Cluster חדש (Free Tier מספיק)
2. צור Database User
3. הוסף IP `0.0.0.0/0` ל-Network Access

#### 2.2 יצירת Vector Search Index
1. לך ל-**Database** → **Atlas Search** → **Create Search Index**
2. בחר **JSON Editor**
3. בחר את ה-Collection: `memory_bot.memories`
4. שם האינדקס: `memories_vector_index`
5. הדבק את ההגדרה:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 1536,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "tags"
    }
  ]
}
```

6. לחץ **Create Index**

### 3. פריסה ב-Render

#### 3.1 יצירת Web Service
1. התחבר ל-Render עם GitHub
2. צור **New Web Service**
3. חבר את ה-Repository
4. הגדרות:
   - **Name**: `memory-bot`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

#### 3.2 הגדרת משתני סביבה
ב-Render, הוסף Environment Variables:

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | טוקן הבוט מ-BotFather |
| `PUBLIC_URL` | `https://your-app.onrender.com` |
| `MONGODB_URI` | Connection string מ-Atlas |
| `DB_NAME` | `memory_bot` |
| `ADMIN_TELEGRAM_ID` | ה-User ID שלך בטלגרם |
| `WEBHOOK_SECRET` | מחרוזת אקראית |
| `OPENAI_API_KEY` | מפתח OpenAI |

#### 3.3 Deploy!
לחץ **Manual Deploy** או חכה ל-Auto Deploy.

### 4. קבלת Telegram User ID

שלח הודעה ל-[@userinfobot](https://t.me/userinfobot) וקבל את ה-ID שלך.

## 📱 שימוש

### שמירת פתרון
1. לחץ **➕ שמור פתרון**
2. הדבק את הפתרון/קוד
3. תן כותרת
4. הוסף תגיות
5. אשר את השמירה

### חיפוש בזיכרון
1. לחץ **🔎 שאל את הזיכרון**
2. שאל בשפה טבעית: "איך פתרנו timeout ברנדר?"
3. קבל תוצאות רלוונטיות

### דוגמאות לשאלות
- "איך פתרנו את בעיית ה-N+1?"
- "מה עשינו עם Redis cache?"
- "טיפול ב-race condition"
- "בעיות ביצועים בדשבורד"

## 📁 מבנה הפרויקט

```
memory-bot/
├── main.py           # הקוד הראשי
├── requirements.txt  # תלויות
├── Procfile          # הרצה ב-Render
├── .env.example      # דוגמה למשתני סביבה
└── README.md         # הקובץ הזה
```

## 🔧 Schema של MongoDB

```javascript
// Collection: memories
{
  _id: ObjectId,
  title: String,           // כותרת קצרה
  solution: String,        // הפתרון המלא
  tags: [String],          // תגיות
  context: String,         // הקשר נוסף
  code: String,            // קוד (אופציונלי)
  embedding: [Number],     // וקטור (1536 dimensions)
  created_at: Date,
  updated_at: Date
}
```

## 🔒 אבטחה

- הבוט **פרטי** - רק ה-Admin יכול להשתמש
- Webhook מוגן עם סוד
- אל תשמור סודות (API keys, passwords) בזיכרונות

## 🐛 פתרון בעיות

### "Vector search לא עובד"
- ודא שיצרת את ה-Vector Index ב-Atlas
- בדוק ששם האינדקס הוא `memories_vector_index`
- ודא ש-`numDimensions` הוא 1536

### "Webhook לא מגיב"
- בדוק שה-`PUBLIC_URL` נכון
- ודא שהשרת למעלה ב-Render

### "Permission denied"
- בדוק שה-`ADMIN_TELEGRAM_ID` נכון
- זה צריך להיות מספר (לא username)

## 📝 רישיון

MIT License

## 🤝 תרומות

נשמח לקבל PRs ו-Issues!

---

נבנה עם ❤️ לפיתרון בעיות
