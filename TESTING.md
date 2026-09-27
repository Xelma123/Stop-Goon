# Stop Goon — Test notları

> **Komutları `cmd` içinde çalıştır, PowerShell'de değil.** `%LocalAppData%` yazımı yalnızca `cmd`'de çalışır. PowerShell penceresindeysen önce `cmd` yazıp Enter'a bas; satır başı `PS` ile başlamamalı.

## Aşama 1 — Kavram kanıtı (tamamlandı)

### Windows sonuçları (kullanıcı, Brave)

| Soru | Sonuç |
|---|---|
| PAC okunuyor mu? | Evet (Brave) |
| Aynı sekmede 302 | Evet, video açıldı |
| Stop Goon kapalı, tarayıcı açık | `ERR_PROXY_CONNECTION_FAILED`, Reddit açılmadı |
| Stop Goon kapalı, tarayıcı yeniden başlatıldı | **Reddit açıldı.** PAC indirilemeyince tarayıcı doğrudan bağlantıya düşüyor. PRD §13'te bilinen sınır; Aşama 4'te değerlendirilecek |
| ~2 MB PAC | **Engel tamamen çalışmadı.** Chromium 1 MiB'ı aşan PAC dosyasını reddediyor (`net/proxy_resolution/pac_file_fetcher_impl.cc`: `kDefaultMaxResponseBytes = 1048576`) |
| Edge, Firefox, `Sec-Fetch-*` başlıkları, `?v=` ile yeniden okuma | Henüz test edilmedi; Aşama 2 testlerinde (I, J, L, P) kontrol edilecek |

### Karar: PAC biçimi (kullanıcı onayı, seçenek 3)

Gerçek `porn-only` listesi (76.797 domain) PRD §7.1'deki biçimle 1,65 MB PAC üretiyordu. Bu, Chromium'un 1 MiB sınırının üstünde. Bu yüzden iki değişiklik yapıldı:

1. **Sadeleştirme:** Üst domaini zaten listede olan alt domainler PAC'e yazılmaz. Eşleşme sonucu değişmez. 76.797 domain → 47.661 girdi.
2. **Hash'li tablo:** PAC'e domain adları yerine 32 bit FNV-1a hash'leri yazılır. PAC artık yalnızca bir ön süzgeç; kesin karar proxy'de, tam listeyle verilir. Hash çakışması (yaklaşık 45.000 hosttan biri) o hostu proxy'ye gönderir. Proxy onu listede bulamaz ve TLS'ini açmadan geçirir.

Sonuç: gerçek listeyle **547 KB** PAC. Ayrıca 1.000.000 baytı aşan bir PAC devreye alınmaz: yeniden yüklemede önceki liste korunur, durum sayfasında uyarı görünür.

---

## Aşama 2 — Tam engelleme

### Linux'ta doğrulananlar (geliştirme ortamı, 27.09.2026)

Ortam: Linux, Python 3.12, mitmproxy 12.2.3, Node.js 22, gerçek StevenBlack `porn-only` listesi (27.09.2026). İstemci olarak `curl` ve `openssl` kullanıldı. **Windows ve gerçek tarayıcılar kullanılmadı.**

| Kontrol | Sonuç |
|---|---|
| Birim testleri | 77/77 geçti |
| Gerçek liste | 76.797 domain, 0 geçersiz satır; yükleme + sadeleştirme + PAC ≈ 0,55 sn |
| 100.000 satırlık liste yükleme | < 1 sn (birim testi) |
| PAC boyutu | 547.656 bayt |
| PAC ↔ Python | JS ve Python hash'leri 5.000 örnekte aynı. Gerçek listeden 10.971 domain ve alt domainleri PAC'te `PROXY` sonucu verdi; `google.com`, `youtube.com`, `wikipedia.org`, `notreddit.com` `DIRECT` |
| Liste yüklemesi | Proxy dinlemeye başlamadan önce tamamlanıyor |
| Bellek | Liste yüklüyken ~83 MB |
| Yasaklı document isteği | 302, TLS el sıkışması dahil 15–22 ms |
| iframe | 403 |
| Sayaç | 5 sn içindeki tekrar sayılmadı, 6 sn sonra sayıldı; `stats.json` doğru |
| Lazy reload | `blocklist.txt`'ye eklenen domain yaklaşık 2 sn içinde PAC'e ve proxy'ye girdi |
| Bozuk `config.json` | Engeller devam etti, durum sayfasında uyarı çıktı |
| Döngü (`youtube.com` listeye eklendi) | Yeni liste reddedildi, önceki liste korundu, uyarı gösterildi |
| `POST /reload` | 303 → durum sayfası |
| Yasaklı olmayan host | TLS açılmadı; yasaklı hostlara hiçbir sunucu bağlantısı açılmadı |

### Windows'ta hazırlık

**1. Kodu güncelle.** GitHub'dan yeni ZIP'i indir ve dosyaları mevcut `stop_goon` klasörünün üzerine çıkar. `.venv` klasörü kalabilir. Sonra testleri çalıştır:

```bat
cd C:\Users\Xelma123\Desktop\stop_goon
.venv\Scripts\python -m pytest -q
```

**2. Liste dosyalarını hazırla.**

```bat
mkdir "%LocalAppData%\StopGoon\lists"
copy samples\blocklist.example.txt "%LocalAppData%\StopGoon\blocklist.txt"
curl -L -o "%LocalAppData%\StopGoon\lists\porn-only.txt" https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/porn-only/hosts
```

`mkdir` "zaten var" derse sorun değil. `copy` komutu dosyanın üzerine yazmak isteyip istemediğini sorarsa `N` de. `curl` yerine adresi tarayıcıda açıp "Farklı kaydet" ile de indirebilirsin. Stop Goon listeyi kendisi indirmez.

**3. Stop Goon'u başlat.**

```bat
.venv\Scripts\mitmdump --listen-host 127.0.0.1 --listen-port 8899 --set confdir=%LocalAppData%\StopGoon\mitmproxy -s stopgoon\addon.py
```

`Blocklist loaded: 76797 domains, PAC 547... bytes` satırını görmelisin. İlk çalıştırmada `config.json` kendiliğinden oluşur.

**4. AutoConfigURL.** Aşama 1'den kalan ayarı Stop Goon artık kendisi günceller (`?v=` değeri). Aşama 1'in sonunda sildiysen:

```bat
.venv\Scripts\python -m stopgoon.winsys set 1
```

**5. Tarayıcıyı tamamen kapatıp aç** (Brave: bildirim alanındaki simge → Çıkış), sonra `http://127.0.0.1:8898/` adresini aç. `Engellenen domain: 76.797` civarı görünmeli ve uyarı olmamalı.

### Elle testler (§17 A–R)

Kullanmadığın tarayıcılar için ilgili satırı atlayabilirsin.

| # | Ne yap | Beklenen | Sonuç |
|---|---|---|---|
| A | Google, Wikipedia, YouTube, e-posta, banka sitesi | Normal; mitmdump penceresinde bu sitelerle ilgili satır yok | |
| B | Adres çubuğuna `reddit.com`, Enter | Aynı sekmede video, baştan | |
| C | `old.reddit.com`, `www.reddit.com` | Video | |
| D | Adres çubuğuna `https://i.redd.it/abc.png` (doğrudan medya linki; yol önemli değil, proxy sunucuya hiç bağlanmaz) | Video | |
| E | Google'da "reddit" ara | Sonuçlar normal görünür | |
| F | Arama sonucundaki Reddit linkine tıkla; bir de orta tıkla (yeni sekme) | İkisinde de video | |
| G | `lists\porn-only.txt` dosyasını Not Defteri'nde aç, rastgele 5 domaini dene | Hepsinde video | |
| H | `redditinc.com` (listede yok, adı benziyor) | Normal açılır | |
| I | Gizli pencere (Brave "Özel pencere", Chrome, Edge) → `reddit.com` | Video | |
| J | Firefox normal + gizli pencere → `reddit.com` | Video, sertifika hatası yok (hata varsa `about:config` → `security.enterprise_roots.enabled` = `true`) | |
| K | Aşağıdaki `test.html` dosyasını aç | Sayfa açılır; görsel ve iframe boş kalır; mitmdump'ta `blocked ... (subresource)` | |
| L | Durum sayfasındaki "Bugün" sayısını not et. Adres çubuğuna `reddit.com` yaz ama **Enter'a basma**, birkaç saniye bekle, sil. Durum sayfasını yenile | Sayı artmamış | |
| M | B'deki video kendiliğinden oynuyor mu, sesli mi? | Oynuyor | |
| N | YouTube'da oturum açıkken videoyu yarıda kapat, sonra tekrar `reddit.com` dene | Video baştan başlar | |
| O | Video açıldıktan sonra geri tuşu | Döngü yok; önceki sayfaya döner | |
| P | `%LocalAppData%\StopGoon\blocklist.txt` dosyasına `example.com` satırı ekle, kaydet, durum sayfasında "Listeyi yeniden yükle"ye tıkla. Tarayıcıyı **kapatmadan** `example.com` aç. Sonra satırı sil ve tekrar "Listeyi yeniden yükle" | Tarayıcı yeniden başlatılmadan video. Satır silinince `example.com` normal açılır | |
| Q | `config.json` dosyasının içeriğini bozup kaydet (örneğin ilk `{` karakterini sil). Durum sayfasını yenile, `reddit.com` dene. Sonra `copy /Y samples\config.example.json "%LocalAppData%\StopGoon\config.json"` ile düzelt | Durum sayfasında uyarı; engel çalışmaya devam eder | |
| R | mitmdump'ı Ctrl+C ile durdur. Tarayıcıyı kapatmadan `reddit.com` ve `wikipedia.org` dene | Reddit açılmaz, Wikipedia normal | |

Ek olarak şunlara bak:
- Normal gezinmede, ~550 KB'lık PAC nedeniyle bir yavaşlık hissediyor musun?
- **`Sec-Fetch-Dest` başlığı:** Geliştirici Araçları (F12) → Ağ (Network) → "Günlüğü koru" (Preserve log) açık → `reddit.com`. `reddit.com` isteğinin başlıklarında `Sec-Fetch-Dest: document` görünüyor mu?

**K için `test.html`:** Not Defteri'ne aşağıdakini yapıştır, masaüstüne `test.html` olarak kaydet ve tarayıcıyla aç.

```html
<!doctype html><meta charset="utf-8">
<p>Bu yazı görünmeli. Altındaki görsel ve çerçeve boş kalmalı.</p>
<img src="https://i.redd.it/test.png" width="200" height="100" style="border:1px solid red">
<iframe src="https://www.reddit.com/" width="300" height="150"></iframe>
```

### Test bitince

Stop Goon'u açık bırakacaksan bir şey yapma. Kaldırmak istersen:

```bat
.venv\Scripts\python -m stopgoon.winsys clear
certutil -user -delstore Root mitmproxy
```
