# Tashih

> PDF dosyalarından çıkarılan metinler için web tabanlı bir musahhihlik (düzeltme) çalışma masası.
> Yapay zekâ olası hataları işaretler; son söz her zaman insan musahhihindir.

[🇬🇧 English](README.md)

---

## Genel Bakış

Birçok belge hâlâ PDF olarak dolaşıyor — kitaplar, tezler, resmi kayıtlar, makaleler — ve bu
metinlerin yeniden yayımlanma, arşivleme veya veri girişi öncesinde düzeltilmesi gerekiyor.
**Tashih**, bu işi yan yana ve adım adım yapılan bir akışa dönüştürür:

1. **Çıkar** — orijinal PDF sayfası ile çıkarılan metin yan yana gösterilir.
2. **Önerir** — bir yapay zekâ modeli metni inceler ve düzeltme önerileri sunar
   (imla, yazım hatası, OCR artıkları, noktalama, tutarlılık).
3. **İnceler** — musahhih her öneriyi kabul, reddet veya düzenler.
4. **Dışa aktarır** — düzeltilmiş metin (ve istenirse temiz bir PDF/DOCX) bir değişiklik
   günlüğü ile birlikte dışa aktarılır.

İnsan kontrolü elinde tutar: yapay zekâ önerileri **asla** otomatik uygulanmaz.

## Temel Özellikler

- 📄 **PDF yükleme ve metin çıkarım** — mümkün olduğunca sayfa/paragraf yapısını korur.
- 🔍 **Yan yana görünüm** — orijinal PDF sayfa görüntüsü ile düzenlenebilir metin.
- 🎈 **Kenar baloncukları** — her öneri asıl PDF sayfasında tespit edilir (metin katmanı üzerinden, **OCR yok**) ve sayfa kenarında renkli bir baloncuk olarak gösterilir: kırmızı = silme, yeşil = ekleme, koyu mor = değiştirme.
- 🖊️ **Musahhih işaretleri** — yazar sayfa görselindeki kelimeye tıklayıp doğrudan işaretler:
  **Sil · Değiştir · Ekle · Boşluk · Birleştir**. Düzeltme anında metne uygulanır ve sayfada
  baloncuk olarak gösterilir.
- 🤖 **Yapay zekâ destekli öneriler** — imla, dilbilgisi, noktalama ve OCR gürültüsü tespiti.
- ✅ **Kabul / reddet / düzenle akışı** — her değişiklik açık ve denetlenebilir.
- 📝 **Doğrudan düzenleme** — musahhih, önerilerin ötesinde metinde serbestçe değişiklik yapabilir.
- 🧾 **Değişiklik günlüğü** — tam fark (orijinal → düzeltilmiş), kim neyi ne zaman değiştirdi.
- 📑 **Toplu işleme** — birden fazla PDF kuyruğa alınır, belge bazında ilerleme izlenir.
- 💾 **Otomatik kaydetme ve devam** — yarım kalan oturum kaldığı yerden sürdürülebilir.
- 📤 **Düzeltme JSON dışa aktarma** — `corrections` (yazar işaretleri) ve `aiSuggestions`
  (yapay zekâ önerileri) alanlarını içeren tek dosya, *Musahhih* masaüstü uygulamasına hazır.
- 🌐 **İki dilli arayüz** — Türkçe ve İngilizce.

## Nasıl Çalışır?

```
┌────────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│ PDF yükleme│ ──▶ │ Metin        │ ──▶ │ YZ analizi    │ ──▶ │ Tashih     │
│            │     │ çıkarma      │     │ (öneriler)    │     │ inceleme UI  │
└────────────┘     └──────────────┘     └───────────────┘     └──────┬───────┘
                                                                     │
                   ┌──────────────┐     ┌───────────────┐           │
                   │ Dışa aktarma │ ◀── │ Değişiklik    │ ◀─────────┘
                   │ (TXT/MD/DOCX)│     │ günlüğü       │
                   └──────────────┘     └───────────────┘
```

## Önerilen Teknoloji Yığını

| Katman      | Teknoloji |
|-------------|-----------|
| Backend     | Python 3.11+, FastAPI, SQLAlchemy, SQLite/PostgreSQL |
| PDF çözümleme | PyMuPDF (fitz) / pdfplumber |
| Yapay zekâ katmanı | OpenAI uyumlu LLM API (sağlayıcı değiştirilebilir) |
| Frontend    | React + Vite, TypeScript |
| Dağıtım     | Docker / Docker Compose |

> Yığın bir öneridir; uygulama sırasında değiştirilebilir.

## Hızlı Başlangıç

### Gereksinimler

- Python 3.11+
- Node.js 20+
- Bir LLM sağlayıcısı için API anahtarı (OpenAI, Anthropic veya yerel model)

### Kurulum

```bash
# 1. Depoyu klonlayın
git clone https://github.com/osmanselvi/tashih.git
cd tashih

# 2. Backend
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # ardından API anahtarınızı girin

# 3. Frontend
cd ../web
npm install

# 4. Çalıştırın (iki ayrı terminalde)
cd ../server && uvicorn app.main:app --reload     # http://localhost:8000
cd ../web && npm run dev                           # http://localhost:5173
```

### Docker (alternatif)

```bash
docker compose up --build
# Uygulama: http://localhost:3000  |  API: http://localhost:8000
```

### Apache2 (yerel dağıtım)

Apache2 kurulu bir makinede Apache derlenmiş frontend'i sunar ve `/api`
isteklerini uvicorn'a yönlendirir:

```bash
# 1. Frontend'i derleyin
cd web && npm install && npm run build && cd ..

# 2. Proxy modüllerini açın (bir kez) ve vhost'u kurun
sudo a2enmod proxy proxy_http
sudo cp web/apache/tashih.conf /etc/apache2/sites-available/tashih.conf
sudo a2ensite tashih
sudo systemctl reload apache2   # veya: sudo apache2ctl restart

# 3. Backend'i çalıştırın (ör. servis olarak veya bir terminalde)
cd server && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Vhost `ServerName tashih.local` kullanır; uygulamaya `http://tashih.local`
adresinden erişilir — `/etc/hosts` dosyasına `127.0.0.1 tashih.local` satırını
ekleyin (veya `ServerName`'i kendi alan adınıza göre düzenleyin). Depo
`/var/www/opencd` yolunda değilse
`/etc/apache2/sites-available/tashih.conf` içindeki `DocumentRoot` yolunu
düzenleyin. Vhost, `web/dist` SPA'sını sunar (var olmayan yollar
`index.html`'e düşer) ve `/api/*` isteklerini backend'e yönlendirir.

### Testler

Backend testleri süreç içinde çalışır (çalışan sunucu gerekmez):

```bash
cd server
python -m pytest -q
```

## Kullanım

1. Web arayüzünü açın ve **bir PDF yükleyin** (veya kuyruktan bir belge seçin).
2. **Çıkarılan metni** orijinal sayfa ile yan yana inceleyin; gerekirse önce çıkarma
   hatalarını düzeltin.
3. Önerileri üretmek için **"Yapay zekâ ile analiz et"** düğmesine tıklayın.
4. Önerileri tek tek **Kabul / Atla / Düzenle** ile değerlendirin — ya da görmezden gelip
   doğrudan elle düzenleyin.
5. İşiniz bitince düzeltilmiş metni **dışa aktarın** (`.txt`, `.md`, `.docx`) ve
   değişiklik günlüğünü indirin.

## Proje Yapısı

```
tashih/
├── server/                 # FastAPI backend
│   ├── app/
│   │   ├── main.py         # Uygulama giriş noktası (derlenmiş frontend'i de sunar)
│   │   ├── config.py       # Ortam değişkenlerinden ayarlar
│   │   ├── db.py           # SQLAlchemy motoru ve oturum
│   │   ├── models.py       # Veritabanı modelleri
│   │   ├── schemas.py      # Pydantic şemaları (API sözleşmesi)
│   │   ├── api/
│   │   │   ├── documents.py    # Yükleme, sayfalar, görüntü, dışa aktarma, analiz
│   │   │   ├── suggestions.py  # Kabul / reddet / geri al
│   │   │   └── common.py       # Seriileştirme yardımcıları
│   │   └── services/
│   │       ├── extractor.py    # PDF → metin + sayfa PNG'leri
│   │       ├── analyzer.py     # YZ / kural tabanlı öneriler
│   │       └── exporter.py     # Sonuçlar → txt / md / docx
│   ├── Dockerfile
│   ├── .env.example
│   └── requirements.txt
├── web/                    # React + Vite frontend
│   ├── Dockerfile, apache/tashih.conf
│   └── src/
│       ├── pages/          # DocumentList (kuyruk), Review (çalışma masası)
│       ├── components/     # SuggestionCard, ChangeLogPanel
│       └── api.ts, types.ts, i18n.ts, styles.css
├── README.md               # İngilizce sürüm
├── README.tr.md            # Bu dosya (Türkçe)
└── docker-compose.yml
```

## Yapılandırma

| Değişken | Açıklama | Varsayılan |
|----------|----------|------------|
| `LLM_API_KEY` | YZ sağlayıcısı API anahtarı; boşsa kural tabanlı analiz yapılır | — |
| `LLM_BASE_URL` | OpenAI uyumlu API adresi | `https://api.openai.com/v1` |
| `LLM_MODEL`   | Öneriler için kullanılacak model | `gpt-4o-mini` |
| `DATABASE_URL`| Veritabanı bağlantı dizesi | `sqlite:///./data/tashih.db` |
| `DATA_DIR`    | Depolama klasörü (yükmeler, sayfa görüntüleri, veritabanı) | `./data` |
| `MAX_UPLOAD_MB` | Azami PDF yükleme boyutu | `50` |
| `LANG` | Varsayılan arayüz dili (`tr` / `en`) | `tr` |

## Yol Haritası

- [ ] PDF yükleme ve sayfaya uygun metin çıkarım
- [ ] Yan yana musahhihlik arayüzü
- [ ] YZ öneri motoru (imla / OCR / noktalama)
- [ ] Kabul/reddet akışı + değişiklik günlüğü
- [ ] TXT / MD / DOCX dışa aktarma
- [ ] Çok kullanıcılı hesaplar ve belgelerin musahhihlere atanması
- [ ] Sözlük / özel dizin desteği
- [ ] İki turlu akış (ilk tur: OCR temizliği, ikinci tur: dil editörlüğü)

## Katkı

Katkılarınız beklenir. Önemli değişiklikler için önce bir issue açın, ardından sorunu ve
çözümü açıklayan bir pull request gönderin.

## Lisans

MIT — ayrıntılar için [LICENSE](LICENSE) dosyasına bakın.
