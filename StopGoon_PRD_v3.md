# Stop Goon — Yerel Proxy ile Reaktif Site Engelleyici

| | |
|---|---|
| **Belge** | Ürün gereksinimleri ve teknik plan (PRD) |
| **Sürüm** | 3.0 |
| **Tarih** | 27 Eylül 2026 |
| **Durum** | Tasarım onaylandı, geliştirme başlamadı |
| **Önceki sürüm** | StopGoon_PRD.md v2.1 (C# + Chrome DevTools Protocol) |

> **Tek cümlelik özet:** Stop Goon, Windows'ta sürekli çalışan küçük bir Python programıdır. Yerel bir proxy açar ve tarayıcılara yalnızca yasaklı domainleri bu proxy'ye göndermelerini söyler. Proxy yalnızca yasaklı bir siteye istek yapıldığında devreye girer ve kullanıcıyı aynı sekmede, site hiç yüklenmeden müdahale videosuna yönlendirir.

---

## 0. v2.1 → v3.0 değişiklik özeti

| Konu | v2.1 | v3.0 | Neden |
|---|---|---|---|
| Dil | C# / .NET 10 | **Python 3.12+** | Kullanıcı tercihi; daha basit |
| Mekanizma | Chrome DevTools Protocol | **Yerel proxy (mitmproxy) + PAC dosyası** | Ağ odaklı, reaktif |
| Kapsam | Yalnızca Stop Goon'un başlattığı Chrome | **Sistem proxy ayarını izleyen tüm tarayıcılar**: Chrome, Edge, Firefox; gizli pencereler ve tüm profiller dahil | Kullanıcı tercihi |
| Tarayıcı başlatma | Stop Goon Chrome'u kendisi başlatıyordu | **Yok.** Kullanıcı istediği tarayıcıyı normal şekilde açar | Basitlik |
| HTTPS yönlendirme | CDP `fulfillRequest` 302 | **Yerel kök sertifika + TLS'i yalnızca yasaklı domainlerde açma + 302** | Proxy'nin HTTPS'te yönlendirme yapabilmesinin tek yolu (§4) |
| Arayüz | WinForms tray | **Yok.** Yerel durum sayfası: `http://127.0.0.1:8898/` | Ek bağımlılık olmasın |
| iframe / gömülü içerik | Engellenmiyordu | **Engelleniyor** (403) | Proxy tüm isteği görür |

Değişmeyenler: müdahale videosu, engel listeleri (`blocklist.txt` + StevenBlack `porn-only`), domain eşleşme kuralları, deneme sayacı, "her zaman açık" davranışı.

---

## 1. Problem ve amaç

Belirli sitelere erişim çoğunlukla bilinçli bir karar değil, anlık bir dürtüyle gerçekleşir. Stop Goon, dürtü ile erişim arasına **otomatik, anlık ve pazarlıksız** bir engel koyar:

```text
Dürtü → yasaklı adrese gitme → [Stop Goon proxy] → site yüklenmez → müdahale videosu
```

**Hedef içerik:** Mastürbasyon materyali içeren siteler ve Reddit'in tamamı.

**Müdahale videosu:** `https://www.youtube.com/watch?v=jkpBEwzAxPo&t=0s`. Video her seferinde baştan başlar (§9.3).

**Reaktiflik ilkesi:** Stop Goon normal internet trafiğini hiç görmez. Proxy yalnızca yasaklı bir domaine istek yapıldığında devreye girer. Zamanlayıcı, polling veya sürekli tarama yoktur.

---

## 2. Kullanıcı ve kullanım şekli

- **Tek kullanıcı**, kişisel bilgisayar, Windows 10/11.
- Kurulum bir kez yapılır. Sonrasında Stop Goon oturum açılışında sessizce başlar.
- Kullanıcı istediği tarayıcıyı normal şekilde kullanır; hiçbir şey fark etmez. Ta ki yasaklı bir siteye girmeye çalışana kadar.
- Engeller **her zaman açıktır**. Zamanlama, odak modu veya geçici kapatma yoktur.

---

## 3. Mimari

```text
                          WINDOWS (kullanıcı oturumu)
   HKCU Internet Settings
   AutoConfigURL = http://127.0.0.1:8898/stopgoon.pac?v=<sürüm>
                │
                │ tarayıcılar PAC dosyasını okur
                ▼
   ┌──────────────────────────────────────────────────────────┐
   │ Tarayıcı (Chrome / Edge / Firefox)                        │
   │ Her istek için PAC: FindProxyForURL(url, host)            │
   │   host yasaklı mı?                                        │
   │     hayır → DIRECT            (Stop Goon hiç görmez)      │
   │     evet  → PROXY 127.0.0.1:8899                          │
   └───────────────────────┬──────────────────────────────────┘
                           │ yalnızca yasaklı domainler
                           ▼
   ┌──────────────────────────────────────────────────────────┐
   │ Stop Goon süreci (pythonw, tek süreç)                     │
   │                                                           │
   │  mitmproxy  127.0.0.1:8899                                │
   │   ├─ tls_clienthello: host yasaklı değilse → TLS'i AÇMA,  │
   │   │                   olduğu gibi geçir (emniyet)         │
   │   └─ requestheaders:                                      │
   │        ön yükleme (prefetch/prerender) → 403, sayma       │
   │        Sec-Fetch-Dest = document        → 302 → video     │
   │                                           sayaç +1        │
   │        diğer (görsel, iframe, xhr...)   → 403             │
   │                                                           │
   │  PAC + durum sunucusu  127.0.0.1:8898                     │
   │   ├─ GET /stopgoon.pac  → üretilmiş PAC dosyası           │
   │   └─ GET /              → durum sayfası (sayaç)           │
   └──────────────────────────────────────────────────────────┘
```

### Neden PAC dosyası?

Alternatif, Windows'un tüm trafiğini proxy'ye göndermesi olurdu. PAC yaklaşımının üstünlükleri:

| | Tüm trafik proxy'ye | PAC ile yalnızca yasaklılar |
|---|---|---|
| Normal gezinmede Stop Goon'un yükü | Her istek | **Sıfır** |
| Stop Goon çökerse | **İnternetin tamamı gider** | Yalnızca yasaklı siteler açılmaz |
| Bankacılık, oyun, uygulamalar | Proxy üzerinden geçer | **Hiç etkilenmez** |
| Python/curl/AI ajanları | Etkilenebilir (Python, Windows proxy ayarını okur) | **Etkilenmez** (PAC'i okumazlar) |
| Reaktiflik | Proxy sürekli çalışır | Proxy yalnızca yasaklı istekte uyanır |

---

## 4. HTTPS neden kök sertifika gerektiriyor?

Tarayıcı bir HTTPS sitesine proxy üzerinden bağlanırken proxy'ye yalnızca `CONNECT reddit.com:443` der, sonrasında trafik uçtan uca şifrelidir. Tarayıcılar, güvenlik gereği `CONNECT` isteğine verilen yönlendirme yanıtlarını **uygulamaz**; bunun yerine bir bağlantı hata sayfası gösterir.

Aynı sekmede 302 ile yönlendirme yapabilmenin tek yolu, proxy'nin yasaklı sitenin TLS bağlantısını kendisinin sonlandırmasıdır. Bunun için:

1. mitmproxy kurulum sırasında **bu bilgisayara özel** bir kök sertifika (CA) üretir.
2. Sertifika Windows'un **kullanıcı** güven deposuna eklenir (yönetici izni gerekmez).
3. Tarayıcı `reddit.com`'a bağlandığında mitmproxy anında `reddit.com` için bir sertifika üretir ve tarayıcı buna güvenir.
4. mitmproxy artık HTTP isteğini görür ve 302 yanıtı verebilir. **Yasaklı sunucuya hiç bağlanılmaz.**

Güvenlik sonuçları ve önlemler §12'de.

---

## 5. Kapsam

### MVP'de olacaklar

- Python paketi + tek süreçte çalışan mitmproxy eklentisi (addon)
- PAC dosyasını ve durum sayfasını sunan küçük yerel HTTP sunucusu (standart kütüphane)
- Kurulum betiği: sanal ortam, CA üretme ve kurma, PAC ayarı, otomatik başlama
- Kaldırma betiği: yapılan her değişikliği geri alır (CA dahil)
- Blocklist: `blocklist.txt` + `lists/porn-only.txt`, hosts formatı desteği
- Yasaklı document navigasyonu → 302 → müdahale videosu
- Yasaklı domainlerden gelen görsel, iframe, script vb. → 403
- Ön yükleme (prefetch/prerender) isteklerinin sayılmadan reddedilmesi
- Yasaklı olmayan hostlarda TLS'in asla açılmaması (emniyet katmanı)
- Yerel deneme sayacı + durum sayfası
- Blocklist değişince yeniden başlatmadan yükleme ve tarayıcılara PAC'i yeniden okutma
- Log dosyası (yalnızca hostname ve zaman)

### MVP'de olmayacaklar

- Tray ikonu, pencere, ayarlar ekranı
- Tarayıcı başlatma veya kontrol etme (CDP, eklenti, WebView2)
- Sistem genelinde tüm trafiğin proxy'lenmesi
- hosts dosyası, DNS, firewall, VPN, WFP/WinDivert değişikliği
- Yasaklı olmayan sitelerin TLS trafiğini açmak veya içeriğini okumak
- Sayfa içeriğini filtrelemek (kelime taraması vb.)
- Veritabanı, bulut, hesap, telemetri
- Listeyi internetten otomatik indirme
- Zamanlama, geçici kapatma
- Anti-tamper

---

## 6. Dosya konumları

```text
%LocalAppData%\StopGoon\
├── app\                 program kodu (stopgoon paketi, run.pyw)
├── venv\                Python sanal ortamı (mitmproxy burada)
├── mitmproxy\           mitmproxy confdir: CA dosyaları (ÖZEL ANAHTAR BURADA)
├── config.json          ayarlar
├── blocklist.txt        kişisel liste: Reddit + ek siteler
├── lists\porn-only.txt  hazır yetişkin içerik listesi (elle indirilir)
├── stats.json           deneme sayacı
└── logs\stopgoon.log    log (1 MB'ı aşınca döndürülür)
```

Yönetici izni gerektiren hiçbir konuma yazılmaz.

---

## 7. Bileşenler

### 7.1 PAC dosyası

Stop Goon, yüklenen blocklist'ten bir PAC dosyası üretir ve `http://127.0.0.1:8898/stopgoon.pac` adresinden sunar. Modern tarayıcılar `file://` PAC adreslerini güvenilir şekilde desteklemediği için dosya HTTP üzerinden sunulur.

**Üretilen PAC'in şekli:**

```javascript
var B = {"reddit.com":1,"redd.it":1,"redditmedia.com":1 /* ... ~77.000 girdi ... */};
var P = "PROXY 127.0.0.1:8899";

function FindProxyForURL(url, host) {
  host = host.toLowerCase();
  if (host.charAt(host.length - 1) == ".") host = host.substring(0, host.length - 1);
  var h = host;
  while (true) {
    if (B.hasOwnProperty(h)) return P;
    var i = h.indexOf(".");
    if (i < 0) return "DIRECT";
    h = h.substring(i + 1);
    if (h.indexOf(".") < 0) return "DIRECT";   // tek etiketli son ek (ör. "com") kontrol edilmez
  }
}
```

Kurallar:

- Eşleşme mantığı Python tarafındaki eşleştiriciyle **birebir aynıdır** (§8.3). İkisi aynı test vektörleriyle test edilir.
- Yasaklı domainler için `DIRECT` yedeği **yoktur**. Stop Goon kapalıysa yasaklı siteler açılmaz, diğer her şey normal çalışır.
- Domainler PAC'e JSON olarak gömülür (`json.dumps`). Böylece kaçış (escaping) hataları olmaz.
- Tarayıcılar PAC'e host'u punycode (xn--...) biçiminde verir; blocklist de aynı biçimde normalize edilir.
- Yanıt başlıkları: `Content-Type: application/x-ns-proxy-autoconfig`, `Cache-Control: no-cache`.

**PAC'i tarayıcılara yeniden okutma:** Blocklist değiştiğinde `AutoConfigURL` değeri yeni bir sürüm parametresiyle yeniden yazılır (`...stopgoon.pac?v=<içerik özeti>`). Ardından WinINET'e ayar değişikliği bildirilir: `InternetSetOptionW` ile `INTERNET_OPTION_SETTINGS_CHANGED` (39) ve `INTERNET_OPTION_REFRESH` (37), `ctypes` üzerinden. Adresin değişmesi, tarayıcıların PAC'i önbellekten değil yeniden indirmesini sağlar.

### 7.2 Windows proxy ayarı

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings
  AutoConfigURL (REG_SZ) = http://127.0.0.1:8898/stopgoon.pac?v=<sürüm>
```

- `ProxyEnable` / `ProxyServer` değerlerine **dokunulmaz** (tüm trafik proxy'lenmez).
- Kurulumdan önce mevcut `AutoConfigURL` değeri varsa (ör. şirket PAC'i) kurulum durur ve kullanıcıyı uyarır. Var olan bir PAC'in üzerine sessizce yazılmaz.
- Kullanıcı arayüzünde bu ayar Windows Ayarlar → Ağ ve İnternet → Proxy → "Kurulum betiği kullan" olarak görünür.

### 7.3 mitmproxy eklentisi

Tek bir addon sınıfı iki kanca (hook) kullanır.

**`tls_clienthello` — emniyet katmanı**

Proxy'ye yasaklı olmayan bir host ulaşırsa (PAC hatası, elle proxy ayarı yapan bir program vb.) o bağlantının TLS'i **açılmaz**, trafik olduğu gibi geçirilir (`ignore_connection = True`).

Host bilgisi SNI'dan değil, **`CONNECT` hedefinden** alınır. Encrypted Client Hello (ECH) açık olduğunda dış SNI gerçek siteyi değil, ağ sağlayıcısının ortak adını gösterebilir. `CONNECT` hedefi ise her zaman gerçek host'tur.

**`requestheaders` — karar**

`requestheaders` kullanılır, gövdesi büyük isteklerde bekleme olmasın diye. `flow.response` bu aşamada atanır ve istek sunucuya hiç gitmez.

```text
host = normalize(flow.request.host)
yasaklı değil → dokunma (emniyet katmanı zaten TLS'i açmamıştır)

yasaklı:
  Sec-Purpose "prefetch" veya "prerender" içeriyor
      → 403, sayma            (ön yükleme; gerçek gezinme ayrıca gelir)

  Sec-Fetch-Dest == "document"
  VEYA (Sec-Fetch-Dest yok VE method GET VE Accept "text/html" içeriyor)
      → 302 Location: redirectUrl
            Cache-Control: no-store
            Referrer-Policy: no-referrer
        sayaç.kaydet(host)

  diğer (iframe, image, script, xhr, video...)
      → 403, boş gövde, Cache-Control: no-store
```

Notlar:

- `Sec-Fetch-Dest` başlığı Chrome, Edge ve Firefox'un güncel sürümlerinde gezinmelerde gönderilir. Yoksa `Accept` başlığı yedek olarak kullanılır.
- Karar tamamen bellek içindedir (set araması). Disk veya ağ erişimi yapılmaz. Sayaç yazımı arka planda yapılır.
- Karar kodundaki beklenmeyen bir hata **403** ile sonuçlanır. Yasaklı bir host için hata durumunda siteyi açmak yerine kapatmak tercih edilir.
- Döngü koruması: `redirectUrl`'nin host'u blocklist'e takılıyorsa config reddedilir (§10.3).

### 7.4 PAC + durum sunucusu

- Standart kütüphane `http.server.ThreadingHTTPServer`, `127.0.0.1:8898`, addon'un `running` kancasında ayrı bir thread olarak başlatılır; `done` kancasında kapatılır.
- Yalnızca iki yol vardır: `/stopgoon.pac` ve `/`. Diğer her şey 404 döner.
- Yalnızca `127.0.0.1`'e bağlanır.

**Durum sayfası (`/`)**, sade tek bir HTML sayfasıdır:

```text
Stop Goon — Aktif
Engellenen domain: 76.812
Bugün: 3 deneme · Toplam: 41
Son deneme: 26.09.2026 22:12
Liste güncellendi: 27.09.2026 00:40
```

### 7.5 Blocklist'in yeniden yüklenmesi

Arka plan thread'i veya dosya izleyicisi kullanılmaz. Değişiklik **tembel (lazy)** şekilde algılanır:

- Proxy'ye veya PAC sunucusuna her istek geldiğinde, en son kontrolden 2 sn geçtiyse `config.json` ve blocklist dosyalarının değişiklik zamanlarına (`os.stat`) bakılır.
- Değişiklik varsa yeni liste tamamen doğrulanıp yüklenir ve tek atamayla devreye alınır. Ardından §7.1'deki "PAC'i yeniden okut" adımı çalışır.
- Ayrıca kaldırma/kurulum betikleri ve durum sayfasındaki bir **"Listeyi yeniden yükle"** bağlantısı (`POST /reload`) yeniden yüklemeyi doğrudan tetikleyebilir.

> Not: Yasaklı siteye hiç istek gelmezse değişiklik yalnızca PAC yeniden indirildiğinde veya "Listeyi yeniden yükle" kullanıldığında algılanır. Kullanıcı listeyi düzenledikten sonra durum sayfasındaki bağlantıya tıklar.

---

## 8. Blocklist

### 8.1 Dosyalar

| Dosya | İçerik | Güncelleme |
|---|---|---|
| `blocklist.txt` | Kişisel liste: Reddit + hazır listede olmayan siteler | Kullanıcı, elle |
| `lists\porn-only.txt` | StevenBlack/hosts `porn-only` (~76.800 domain, MIT) | Kullanıcı, ayda bir elle |

**`blocklist.txt` başlangıç içeriği:**

```text
# ── Reddit ──────────────────────────────────────────
# Alt domainler otomatik engellenir (www., old., i.redd.it, v.redd.it ...)
reddit.com
redd.it
redditmedia.com
reddit.app.link

# ── Kişisel eklemeler ───────────────────────────────

# ── İsteğe bağlı: Google Çeviri site proxy'si ───────
# translate.goog
```

**Hazır listenin kurulumu:** `https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/porn-only/hosts` adresini aç, `%LocalAppData%\StopGoon\lists\porn-only.txt` olarak kaydet, durum sayfasında "Listeyi yeniden yükle"ye tıkla.

Birleşik (reklam + zararlı yazılım + yetişkin) liste **kullanılmaz**. Reklam ve izleyici domainleri e-posta linklerindeki yönlendirme zincirlerinde sık geçer ve sıradan linkleri videoya düşürür.

### 8.2 Ayrıştırma

- Boş satırlar ve `#` ile başlayan satırlar atlanır; satır sonu yorumları kesilir.
- Hosts formatı: satır `0.0.0.0` veya `127.0.0.1` ile başlıyorsa ikinci parça alınır.
- `localhost`, `0.0.0.0`, `broadcasthost`, `local` gibi özel adlar atlanır.
- Baştaki `*.` ve `.` kaldırılır.
- Geçersiz satırlar atlanır ve satır numarasıyla loglanır.

### 8.3 Normalizasyon ve eşleşme

Normalizasyon: küçük harf → sondaki `.` kaldır → IDN ise `idna` codec ile punycode'a çevir.

Eşleşme: etiket etiket son ek yürüyüşü, `set` üzerinde. `site.com` engelliyse:

```text
site.com, www.site.com, a.b.site.com   → engelle
notsite.com, site.com.evil.example     → izin ver
com                                     → izin ver (tek etiket)
```

`in` ile alt dize araması (`"site.com" in host`) **kullanılmaz**.

---

## 9. Müdahale ve sayaç

### 9.1 Yönlendirme

`302 Found`, `Location: https://www.youtube.com/watch?v=jkpBEwzAxPo&t=0s`

- Yasaklı sunucuya hiç bağlanılmaz.
- Adres çubuğu video adresini gösterir; geri tuşu döngüye girmez.
- YouTube PAC'te yasaklı olmadığı için `DIRECT` gider; Stop Goon video trafiğini görmez.

### 9.2 Otomatik oynatma

Tarayıcılar, kullanıcı etkileşimi olmadan sesli otomatik oynatmayı kısıtlayabilir. Ancak yönlendirme kullanıcının kendi tıklaması veya Enter'ı ile başlayan bir gezinmenin devamı olduğundan YouTube genellikle oynatır. Bu, test M ile doğrulanır. Proxy yaklaşımı tarayıcı başlatma parametrelerini kontrol etmediği için ek bir önlem alınmaz.

### 9.3 Baştan başlama

`&t=0s` parametresi, YouTube'da oturum açıkken yarıda bırakılan videonun kaldığı yerden sürmesini engeller.

### 9.4 Deneme sayacı

`stats.json`:

```json
{ "total": 41, "days": { "2026-09-26": 3 }, "lastAttemptUtc": "2026-09-26T19:12:44Z" }
```

- Yalnızca 302 verilen document istekleri sayılır. 403'ler ve ön yüklemeler sayılmaz.
- Aynı yasaklı domain için 5 sn içindeki tekrarlar tek deneme sayılır.
- Gün sınırı yerel saate göredir.
- Yazım atomiktir (geçici dosya → `os.replace`). Bozuk dosya `stats.json.bak` olarak saklanır ve sayaç sıfırdan başlar.

---

## 10. Config

### 10.1 `config.json`

```json
{
  "redirectUrl": "https://www.youtube.com/watch?v=jkpBEwzAxPo&t=0s",
  "blocklistFiles": ["blocklist.txt", "lists/porn-only.txt"],
  "proxyPort": 8899,
  "pacPort": 8898
}
```

### 10.2 Yükleme

Göreli yollar `%LocalAppData%\StopGoon\` altına göre çözülür.

### 10.3 Doğrulama ve hata davranışı

| Durum | Davranış |
|---|---|
| `config.json` yok | Varsayılanla oluşturulur |
| JSON bozuk | Son geçerli config korunur, log'a hata yazılır, durum sayfasında gösterilir |
| `redirectUrl` https değil | Reddedilir, son geçerli config korunur |
| `redirectUrl` host'u blocklist'te | Reddedilir (döngü riski) |
| Blocklist dosyası yok | O dosya atlanır, diğerleri yüklenir, durum sayfasında uyarı |
| Port kullanımda | Başlatma başarısız olur, log'a açık hata yazılır |

İlke: **Bir yazım hatası ne interneti kapatmalı ne de engelleri kaldırmalı.**

---

## 11. Kurulum, çalıştırma, kaldırma

### 11.1 Ön koşul

Python 3.12 veya üzeri (python.org yükleyicisi; `py` başlatıcısı ile). mitmproxy 12.x, Python 3.12+ gerektirir.

### 11.2 `install.py` (tek komut: `py -3 install.py`)

```text
1. %LocalAppData%\StopGoon\ klasörlerini oluştur, kodu app\ altına kopyala.
2. venv oluştur; pip ile mitmproxy'yi kur (sürüm requirements.txt'de sabitlenir).
3. Varsayılan config.json ve blocklist.txt yoksa oluştur.
4. CA'yı üret: mitmproxy'yi confdir = ...\mitmproxy ile bir kez kısa süre başlat/durdur.
5. CA'yı kullanıcı güven deposuna ekle:
     certutil -user -addstore Root "<confdir>\mitmproxy-ca-cert.cer"
   Windows bir güvenlik uyarısı gösterir; kullanıcı "Evet" der.
6. Mevcut AutoConfigURL varsa DUR ve uyar.
   Yoksa AutoConfigURL'yi yaz, WinINET'e bildir.
7. HKCU\...\Run\StopGoon = "<venv>\Scripts\pythonw.exe" "<app>\run.pyw"
8. Stop Goon'u başlat.
9. Kullanıcıya şunları yazdır: durum sayfası adresi, porn-only listesinin nasıl
   indirileceği, tarayıcıların yeniden başlatılması gerektiği.
```

Her adım idempotenttir: kurulum iki kez çalıştırılırsa bozulma olmaz.

### 11.3 `run.pyw`

- Konsol penceresi açmadan (`pythonw`) çalışır.
- mitmproxy'yi süreç içinde başlatır: `mitmproxy.tools.main.mitmdump(args)`. Argümanlar: `--listen-host 127.0.0.1`, `--listen-port <proxyPort>`, `--set confdir=<...>`, `-q`, `-s <addon yolu>`.
- **Tek örnek:** PAC portu zaten doluysa ve durum sayfası "Stop Goon" yanıtı veriyorsa, ikinci örnek sessizce çıkar.
- Başlangıçta `AutoConfigURL`'yi doğrular. Ayar silinmiş veya değişmişse yeniden yazmaz, log'a uyarı yazar. Kullanıcı ayarı bilinçli değiştirmiş olabilir; geri koymak `install.py`'nin işidir.

### 11.4 `uninstall.py`

Kurulumun yaptığı her şeyi ters sırayla geri alır:

1. Çalışan Stop Goon'u durdur.
2. `AutoConfigURL`'yi sil (yalnızca değer Stop Goon'a aitse) ve WinINET'e bildir.
3. Run kaydını sil.
4. CA'yı kullanıcı güven deposundan kaldır.
5. `mitmproxy\` klasörünü (özel anahtar) sil.
6. İsteğe bağlı: tüm `%LocalAppData%\StopGoon\` klasörünü sil (kullanıcıya sorulur; sayaç ve listeler burada).

**Kaldırma, CA'yı mutlaka kaldırmalıdır.** Kullanılmayan bir kök sertifikanın sistemde kalması gereksiz bir risktir.

---

## 12. Güvenlik

### 12.1 Kök sertifika riski

`mitmproxy-ca.pem` dosyası kök sertifikanın **özel anahtarını** içerir. Bu anahtarı okuyabilen bir program, bu bilgisayarda herhangi bir site için tarayıcının güveneceği sahte sertifikalar üretebilir.

Önlemler:

| Önlem | Açıklama |
|---|---|
| Kuruluma özel CA | mitmproxy CA'yı ilk çalıştırmada benzersiz üretir; başka bilgisayarlarla paylaşılmaz |
| Kullanıcı deposu | CA yalnızca bu Windows kullanıcısı için güvenilir; makine geneline kurulmaz |
| Anahtar yalnızca kullanıcı klasöründe | `%LocalAppData%` altında; dosya asla kopyalanmaz, yedeklenmez, paylaşılmaz |
| TLS yalnızca yasaklı hostlarda açılır | PAC + `tls_clienthello` emniyeti: banka, e-posta vb. trafiğin şifresi Stop Goon tarafından hiç çözülmez |
| Yalnızca localhost | Proxy ve PAC sunucusu yalnızca `127.0.0.1`'e bağlanır |
| Log'da içerik yok | Yalnızca hostname ve zaman loglanır; URL yolu, başlık, çerez loglanmaz |
| Kaldırma | CA ve özel anahtar silinir |

**Kabul edilen risk:** Bilgisayarda kullanıcı yetkisiyle çalışan kötü amaçlı bir yazılım özel anahtarı okuyabilir. Ancak böyle bir yazılım zaten tarayıcı çerezlerine ve dosyalara erişebilir; kişisel kullanım için bu risk kabul edilmiştir.

### 12.2 Tarayıcı güveni

- **Chrome ve Edge:** Windows kullanıcı deposundaki kök sertifikalara güvenir. Yerel kurulu kök sertifikalar HSTS'li siteler için de geçerlidir.
- **Firefox:** Kendi sertifika deposunu kullanır. Windows'taki kurumsal/kullanıcı köklerini içe alma ayarı (`security.enterprise_roots.enabled`) Aşama 1'de kontrol edilir. Kapalıysa `about:config` üzerinden açılır veya CA Firefox'a elle içe aktarılır. README'de adım adım anlatılır.

---

## 13. Bypass modeli ve bilinen kaçış yolları

Stop Goon, bilgisayarın sahibine karşı mutlak koruma sağlamaz. Amaç dürtü ile erişim arasına otomatik bir engel koymaktır.

| Kaçış yolu | Durum | Not |
|---|---|---|
| Chrome, Edge, Firefox (varsayılan proxy ayarıyla) | **Kapalı** | PAC sistem ayarından okunur |
| Gizli pencere, diğer profiller, misafir modu | **Kapalı** | Aynı proxy ayarı |
| Yeni sekme, popup, yer imi, geçmiş, arama sonucu linki | **Kapalı** | Hepsi document isteği |
| İzinli siteden yasaklı siteye yönlendirme | **Kapalı** | Yeni istek PAC'ten geçer |
| Başka sitelere gömülü yasaklı içerik (görsel, iframe, video) | **Kapalı** | 403 |
| `i.redd.it`, `v.redd.it`, `reddit.app.link` | **Kapalı** | Listede |
| DNS-over-HTTPS, alternatif DNS | **Kapalı** | PAC DNS'ten önce, host adına göre karar verir |
| Tarayıcı içi VPN/proxy eklentisi | **Açık** | Eklentinin proxy ayarı sistem ayarını geçersiz kılar |
| Firefox'ta "proxy yok" ayarı, Tor Browser | **Açık** | Kendi proxy ayarları var |
| Windows proxy ayarından "Kurulum betiği"ni kapatmak | **Açık (kabul edildi)** | |
| Stop Goon'u kapatmak | **Kısmen** | Yasaklı siteler açılmaz (PAC `DIRECT` yedeği yok). Ancak tarayıcı PAC'i yeniden indirmeye çalışıp alamazsa doğrudan bağlantıya düşer |
| Sistem genelinde VPN | **Kısmen** | Tarayıcılar PAC'i okumaya devam eder; 127.0.0.1 erişilebilir kaldıkça çalışır; test edilir |
| Reddit ayna/alternatif ön yüzleri, listede olmayan yeni siteler | **Açık** | Listeye eklenerek kapatılır |
| IP adresiyle doğrudan erişim | **Açık** | Nadir; IP listeye eklenebilir |
| Google Görseller, arama önizlemeleri | **Açık** | Aşama 4'te isteğe bağlı SafeSearch zorlaması |

---

## 14. AI ajanları ve diğer araçlar

```text
Tarayıcılar (sistem proxy ayarını kullanan)  → PAC uygulanır
Python requests / urllib                     → etkilenmez (PAC'i değil, yalnızca ProxyServer'ı okur;
                                               Stop Goon ProxyServer'a dokunmaz)
curl                                         → etkilenmez
Playwright / Puppeteer                       → varsayılan olarak etkilenmez
Oyunlar, uygulama güncellemeleri, bankacılık → etkilenmez
```

Stop Goon `ProxyServer`/`ProxyEnable` değerlerini **asla** değiştirmez. Bu kural, yukarıdaki izolasyonun temelidir.

---

## 15. Fonksiyonel olmayan gereksinimler

| Konu | Gereksinim |
|---|---|
| Normal gezinmeye etkisi | Ölçülebilir fark yok; normal trafik proxy'den geçmez |
| PAC boyutu | ~77.000 domainle ~2 MB; tarayıcı değerlendirme süresi ihmal edilebilir (Aşama 1'de ölçülür) |
| Yasaklı istek yanıt süresi | < 50 ms (TLS el sıkışması dahil, sertifika önbelleklendikten sonra) |
| Bellek | Boşta < 150 MB |
| CPU | Boşta ~%0 |
| Blocklist yükleme | 100.000 satır < 1 sn |
| Başlangıç | Oturum açılışından sonra < 5 sn içinde hazır |
| Gizlilik | Hiçbir veri bilgisayardan çıkmaz |
| Yönetici izni | Gerekmez |
| Platform | Windows 10 22H2 / Windows 11, Python 3.12+ |
| Dil | Kullanıcıya görünen metinler Türkçe; kod ve yorumlar İngilizce |

---

## 16. Klasör yapısı (kaynak kod)

```text
StopGoon/
├── stopgoon/
│   ├── __init__.py
│   ├── addon.py        mitmproxy addon: tls_clienthello, requestheaders, running, done
│   ├── blocklist.py    ayrıştırma, normalizasyon, eşleşme
│   ├── pac.py          PAC metni üretimi
│   ├── server.py       PAC + durum sunucusu (http.server)
│   ├── stats.py        deneme sayacı
│   ├── config.py       yükleme, doğrulama, son geçerli config, lazy reload
│   ├── winsys.py       kayıt defteri, WinINET bildirimi (ctypes), certutil
│   └── paths.py
├── run.pyw
├── install.py
├── uninstall.py
├── requirements.txt    mitmproxy==<sabit sürüm>
├── tests/
│   ├── test_blocklist.py
│   ├── test_pac.py        üretilen PAC'i Python eşleştiricisiyle aynı vektörlerle test eder (§17)
│   ├── test_addon.py      mitmproxy.test.tflow ile sahte akışlar
│   ├── test_config.py
│   └── test_stats.py
├── samples/
│   ├── config.example.json
│   └── blocklist.example.txt
├── README.md           Türkçe kurulum ve kullanım
└── TESTING.md
```

**Bağımlılıklar:** Çalışma zamanında yalnızca `mitmproxy`. Testlerde `pytest`. Diğer her şey standart kütüphane (`http.server`, `winreg`, `ctypes`, `json`, `subprocess`).

---

## 17. Test planı

### Birim testleri

- **Blocklist:** yorumlar, hosts formatı, `*.` öneki, geçersiz satırlar, IDN, sondaki nokta, 100.000 satırın yükleme süresi.
- **Eşleşme:** §8.3'teki vektörler.
- **PAC/Python tutarlılığı:** Aynı test vektörleri hem Python eşleştiricisine hem üretilen PAC'e uygulanır. PAC'i çalıştırmak için test ortamında Node.js varsa kullanılır, yoksa test atlanır ve bu raporlanır.
- **Addon** (`mitmproxy.test.tflow` ile):
  - document → 302 + doğru `Location`
  - image / iframe → 403
  - `Sec-Purpose: prefetch` → 403, sayaç artmaz
  - yasaksız host → dokunulmaz
  - karar kodunda istisna → 403
- **Config:** bozuk JSON, http URL, döngü riski, eksik dosya.
- **Sayaç:** 5 sn tekilleştirme, gün değişimi, bozuk dosya.

### Entegrasyon testleri (elle, Windows'ta)

| # | Senaryo | Beklenen |
|---|---|---|
| A | Google, Wikipedia, YouTube, e-posta, banka | Normal; Stop Goon log'unda iz yok |
| B | Adres çubuğuna `reddit.com` | Aynı sekmede video, baştan |
| C | `old.reddit.com`, `www.reddit.com` | Video |
| D | `i.redd.it/...` doğrudan medya linki | Video |
| E | Google'da "reddit" araması | Sonuçlar normal |
| F | Arama sonucundaki Reddit linki (normal ve orta tık) | Video |
| G | `porn-only` listesinden rastgele 5 domain | Video |
| H | Benzer ama yasaksız domain | Normal |
| I | Gizli pencere (Chrome, Edge) | Video |
| J | Firefox (normal + gizli) | Video; sertifika hatası yok |
| K | Yasaklı siteden gömülü içerik barındıran izinli sayfa | Sayfa açılır, gömülü içerik boş |
| L | Adres çubuğuna yasaklı adres yazıp Enter'a basmamak | Sayaç artmaz |
| M | Video otomatik oynuyor mu, sesli mi | Oynuyor |
| N | Video yarıda kapatılıp tekrar deneme (YouTube'da oturum açık) | Baştan başlar |
| O | Geri tuşu | Döngü yok |
| P | `blocklist.txt`'ye domain ekle → "Listeyi yeniden yükle" | Tarayıcı yeniden başlatılmadan engellenir |
| Q | `config.json` bozuldu | Engeller devam eder |
| R | Stop Goon kapatıldı | Yasaklı siteler açılmaz, diğerleri normal |
| S | Bilgisayar yeniden başlatıldı | Stop Goon kendiliğinden hazır |
| T | Python `requests.get("https://www.reddit.com")`, `curl` | Etkilenmez |
| U | Sistem VPN'i açıkken B | Video (veya bilinen sınır olarak raporlanır) |
| V | `uninstall.py` | AutoConfigURL, Run kaydı, CA ve anahtar kaldırılmış |
| W | `install.py` iki kez | Bozulma yok |

---

## 18. Kabul kriterleri

- [ ] Yönetici izni olmadan kurulup kaldırılabiliyor.
- [ ] Oturum açılışında sessizce başlıyor; konsol penceresi yok.
- [ ] Normal trafik Stop Goon'dan geçmiyor.
- [ ] Yasaklı olmayan hiçbir hostun TLS trafiği açılmıyor.
- [ ] Yasaklı document isteği aynı sekmede 302 ile videoya gidiyor; yasaklı sunucuya bağlantı kurulmuyor.
- [ ] Yasaklı domainlerden gömülü içerik 403 alıyor.
- [ ] Ön yüklemeler sayılmıyor.
- [ ] Chrome, Edge ve Firefox'ta (gizli pencere dahil) çalışıyor.
- [ ] Blocklist değişikliği yeniden başlatmadan uygulanıyor; bozuk config engelleri kaldırmıyor.
- [ ] Sayaç doğru; durum sayfasında görünüyor.
- [ ] `ProxyServer`/`ProxyEnable` değiştirilmiyor; Python/curl etkilenmiyor.
- [ ] Kaldırma, CA ve özel anahtar dahil her şeyi geri alıyor.
- [ ] Birim testleri geçiyor; §17 entegrasyon senaryoları elle doğrulandı.

---

## 19. Geliştirme aşamaları

### Aşama 1 — Kavram kanıtı (elle çalıştırma, kurulum betiği yok)

1. venv + mitmproxy.
2. Yalnızca `reddit.com` içeren sabit bir blocklist ile addon + PAC sunucusu.
3. `mitmdump -s ...` ile elle başlat; `AutoConfigURL`'yi elle ayarla; CA'yı elle kur.
4. **Doğrula ve `TESTING.md`'ye yaz:**
   - Chrome, Edge, Firefox PAC'i okuyor mu?
   - Aynı sekmede 302 çalışıyor mu? Adres çubuğu ne gösteriyor?
   - `Sec-Fetch-Dest` ve `Sec-Purpose` başlıkları beklendiği gibi geliyor mu?
   - `tls_clienthello`'da `CONNECT` hedefine erişim nasıl sağlanıyor? (mitmproxy API'si doğrulanır)
   - ~2 MB'lık PAC'in tarayıcılarda yükleme ve değerlendirme süresi
   - `AutoConfigURL` değişince (`?v=` ile) tarayıcılar PAC'i yeniden okuyor mu?
   - Firefox kök sertifikaya güveniyor mu?
   - Stop Goon kapalıyken tarayıcılar ne yapıyor?

### Aşama 2 — Tam engelleme

Blocklist ayrıştırıcı ve eşleştirici, PAC üretimi, tam karar mantığı, config doğrulama, lazy reload, sayaç, durum sayfası, birim testleri. §17 A–R elle doğrulanır.

### Aşama 3 — Kurulum ve günlük kullanım

`install.py`, `run.pyw`, `uninstall.py`, tek örnek koruması, log döndürme, Türkçe README. §17'nin tamamı.

### Aşama 4 — İsteğe bağlı (MVP sonrası)

- **SafeSearch zorlaması:** `google.*` arama domainlerini PAC'e ekle; addon, `safe=active` içermeyen arama isteklerini `safe=active` eklenmiş URL'ye 302 ile yönlendirir. Bu, TLS'in Google aramalarında da açılması demektir; güvenlik bedeli README'de açıkça yazılır.
- Stop Goon kapatıldığında tarayıcıların doğrudan bağlantıya düşmesini zorlaştıran bir önlem.

**Kural:** Bir aşama çalışmadan sonrakine geçilmez.

---

## 20. Yapılmaması gerekenler

```text
❌ ProxyServer / ProxyEnable değiştirmek (tüm trafiği proxy'lemek)
❌ Yasaklı olmayan hostların TLS'ini açmak
❌ CA'yı makine geneline (LocalMachine) kurmak
❌ Özel anahtarı kopyalamak, loglamak, başka yere taşımak
❌ Mevcut bir AutoConfigURL'nin üzerine sessizce yazmak
❌ URL yolu, başlık, çerez veya içerik loglamak
❌ Sayfa içeriğini okumak veya filtrelemek
❌ Tray/GUI kütüphanesi, web çatısı (Flask vb.), veritabanı
❌ hosts, DNS, firewall, WFP, VPN değişikliği
❌ Listeyi internetten indirmek
❌ Telemetri, bulut, hesap
❌ Periyodik zamanlayıcı veya polling döngüsü
❌ mitmproxy dışında çalışma zamanı bağımlılığı
```

---

## 21. Riskler

| Risk | Olasılık | Etki | Önlem |
|---|---|---|---|
| Özel anahtarın kötüye kullanılması | Düşük | Yüksek | §12 |
| Büyük PAC dosyası bir tarayıcıda yavaş veya sınırlı | Düşük | Orta | Aşama 1'de ölçülür. Sorun çıkarsa ajan durur ve alternatifleri kullanıcıya sunar; mimari kendi başına değiştirilmez |
| Tarayıcılar PAC değişikliğini algılamaz | Orta | Düşük | `?v=` sürüm parametresi + WinINET bildirimi; olmazsa tarayıcı yeniden başlatılır |
| Firefox CA'ya güvenmez | Orta | Orta | README'de ayar adımı |
| mitmproxy API değişiklikleri | Orta | Orta | Sürüm `requirements.txt`'de sabitlenir |
| Tarayıcı eklentisi proxy ayarını ezer | Düşük | Orta | Kabul edilen sınır |
| YouTube otomatik oynatmaz | Orta | Düşük | Test M |
| Stop Goon kapalıyken tarayıcı doğrudan bağlantıya düşer | Orta | Orta | Kabul edildi; Aşama 4'te değerlendirilir |

---

## 22. Kararlar

| Konu | Karar |
|---|---|
| Ad | Stop Goon |
| Hedef | Mastürbasyon materyali içeren siteler + Reddit |
| Mekanizma | Python + mitmproxy + PAC, yerel kök sertifika |
| Kapsam | Sistem proxy ayarını kullanan tüm tarayıcılar |
| Müdahale | Aynı sekmede 302 → `https://www.youtube.com/watch?v=jkpBEwzAxPo&t=0s` |
| Engelleme zamanı | Her zaman açık |
| Listeler | `blocklist.txt` + StevenBlack `porn-only` |
| Ek özellik | Yerel deneme sayacı + durum sayfası |

---

## 23. Teknik referanslar

- mitmproxy belgeleri: `docs.mitmproxy.org` — Event hooks (`requestheaders`, `tls_clienthello`, `running`, `done`), `mitmproxy.http.Response.make`, sertifikalar ve `confdir`
- mitmproxy PyPI: sürüm 12.2.3, Python ≥ 3.12
- MDN — Proxy Auto-Configuration (PAC) dosyası, `FindProxyForURL`
- MDN — `Sec-Fetch-Dest`, `Sec-Purpose` istek başlıkları
- Microsoft — `InternetSetOption` (`INTERNET_OPTION_SETTINGS_CHANGED`, `INTERNET_OPTION_REFRESH`), `certutil -user -addstore`
- StevenBlack/hosts — `alternates/porn-only/hosts`

Uygulama sırasında tüm API adları güncel belgelerden doğrulanmalıdır.
