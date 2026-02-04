# הוראות לעבודה על הפרויקט

## שפה וסיכומים

- **סכם את כל השינויים בצ'אט בעברית**
- **סכם תיאורי PR בעברית**
- דבר עם המשתמש בעברית כברירת מחדל

## גישה לפתרון באגים

- **תמיד הצע את הפתרון השורשי והאמין ביותר** - אל תתקן סימפטומים, תקן את הסיבה האמיתית
- לפני הצעת פתרון, הבן את הבעיה לעומק
- העדף פתרונות פשוטים ונקיים על פני workarounds

## מבנה הפרויקט

```
MemoryBot/
├── main.py          # קובץ ראשי - FastAPI + Telegram Bot
├── requirements.txt # תלויות Python
├── render.yaml      # הגדרות Render
├── Procfile         # פקודת הפעלה
└── CLAUDE.md        # קובץ זה
```

## טכנולוגיות

- **Backend**: FastAPI + Uvicorn
- **Bot**: python-telegram-bot (webhook mode)
- **Database**: MongoDB Atlas עם Vector Search
- **Embeddings**: OpenAI text-embedding-3-small (1536 dimensions)
- **Hosting**: Render.com

## משתני סביבה נדרשים

| משתנה | תיאור |
|-------|-------|
| `BOT_TOKEN` | טוקן הבוט מ-BotFather |
| `PUBLIC_URL` | כתובת השרת הציבורית (ללא / בסוף) |
| `MONGODB_URI` | Connection string של MongoDB Atlas |
| `OPENAI_API_KEY` | מפתח API של OpenAI |
| `ADMIN_TELEGRAM_ID` | מזהה Telegram של המנהל |
| `WEBHOOK_SECRET` | סוד ל-webhook (יכול להכיל / ותווים מיוחדים) |

## בעיות נפוצות ופתרונות

### Webhook 404
**בעיה**: Telegram שולח לwebhook וחוזר 404
**פתרון שורשי**: ה-`WEBHOOK_SECRET` מכיל `/` שFastAPI מפרש כpath separator. השתמש ב-`{secret:path}` במקום `{secret}` בהגדרת הroute.

### Vector Search לא עובד
**בעיה**: חיפוש סמנטי לא מחזיר תוצאות
**פתרון**: ודא שיצרת את ה-Vector Search Index ב-MongoDB Atlas (ראה הוראות למטה)

## יצירת Vector Search Index ב-MongoDB Atlas

1. היכנס ל-MongoDB Atlas
2. לך ל-**Database** → בחר את ה-cluster
3. לחץ על **Atlas Search** (לא על Indexes רגיל!)
4. לחץ **Create Search Index**
5. בחר **JSON Editor**
6. בחר את ה-database והcollection: `memory_bot.memories`
7. שם האינדקס: `memories_vector_index`
8. הדבק את ה-JSON:

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
    },
    {
      "type": "filter",
      "path": "created_at"
    }
  ]
}
```

**חשוב**: הכפתור יהיה אפור אם:
- אין documents עם שדה `embedding` ב-collection (זה בסדר, אפשר ליצור בכל זאת)
- אתה בממשק הלא נכון (צריך Atlas Search, לא Indexes)

## פקודות שימושיות

```bash
# הרצה מקומית
uvicorn main:app --reload --port 8000

# בדיקת תקינות
curl http://localhost:8000/

# סטטיסטיקות
curl http://localhost:8000/stats
```
