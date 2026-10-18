# Stop Goon — Test notları

## Aşama 1 — Kavram kanıtı

Bu aşamada kurulum betiği yoktur. Her şey elle yapılır. Blocklist sabittir ve yalnızca `reddit.com` içerir (alt domainler dahil).

### 1. Hazırlık (Windows, `cmd.exe`, depo kök klasöründe)

```bat
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt pytest
.venv\Scripts\python -m pytest -q
```

### 2. Proxy'yi başlat

```bat
.venv\Scripts\mitmdump --listen-host 127.0.0.1 --listen-port 8899 --set confdir=%LocalAppData%\StopGoon\mitmproxy -s stopgoon\addon.py
```

- İlk çalıştırmada CA dosyaları `%LocalAppData%\StopGoon\mitmproxy\` altında üretilir.
- PAC ve durum sayfası: `http://127.0.0.1:8898/stopgoon.pac` ve `http://127.0.0.1:8898/`.
- Büyük PAC ölçümü için komuta `--set stopgoon_pac_padding=77000` ekle. Bu, PAC'e 77.000 sahte `.invalid` girdisi ekler (~2 MB). Bu girdiler gerçek sitelerle eşleşmez.
- Addon başlarken `connection_strategy=lazy`, `rawtcp=false` ve `flow_detail=0` değerlerini kendisi ayarlar (bkz. "Linux'ta doğrulananlar").

### 3. CA'yı kullanıcı deposuna kur

```bat
certutil -user -addstore Root "%LocalAppData%\StopGoon\mitmproxy\mitmproxy-ca-cert.cer"
```

Windows bir güvenlik uyarısı gösterir; "Evet" de. `-user` bayrağı zorunludur (makine geneline kurulmaz).

Geri almak için: `certutil -user -delstore Root mitmproxy`

### 4. AutoConfigURL'yi ayarla

Önce mevcut değeri kontrol et:

```bat
.venv\Scripts\python -m stopgoon.winsys show
```

`(yok)` dışında bir değer görürsen **devam etme**; bu başka bir PAC'tir (ör. şirket). Değer yoksa:

```bat
.venv\Scripts\python -m stopgoon.winsys set 1
```

Bu komut yalnızca `AutoConfigURL` değerini yazar ve WinINET'e bildirir. `ProxyEnable`/`ProxyServer` değerlerine dokunmaz. Başka birine ait bir değer varsa üzerine yazmaz.

Geri almak için: `.venv\Scripts\python -m stopgoon.winsys clear`

### 5. Başlıkları görmek

Log'a başlık yazılmaz. `Sec-Fetch-Dest` ve `Sec-Purpose` değerlerini görmek için tarayıcının Geliştirici Araçları → Ağ (Network) sekmesini kullan ("Preserve log" / "Günlüğü koru" açık). mitmdump konsolunda her karar için yalnızca host ve karar türü görünür: `redirected <host>`, `blocked <host> (subresource)`, `blocked <host> (prefetch)`.

---

### Linux'ta doğrulananlar (geliştirme ortamı, 27.09.2026)

Ortam: Linux, Python 3.12, mitmproxy 12.2.3, Node.js 22. **Windows ve gerçek tarayıcılar kullanılmadı.** İstemci olarak `curl` ve `openssl s_client` kullanıldı.

| Kontrol | Sonuç |
|---|---|
| Birim testleri (`pytest`) | 34/34 geçti |
| PAC ↔ Python eşleştirici tutarlılığı (Node.js ile PAC çalıştırıldı) | Aynı sonuç |
| `GET /stopgoon.pac` | 200, `application/x-ns-proxy-autoconfig`, `Cache-Control: no-cache` |
| `GET /` / diğer yollar | Durum sayfası / 404 |
| HTTPS `www.reddit.com`, `Sec-Fetch-Dest: document` | 302, `Location` doğru, `no-store`, `no-referrer` |
| HTTPS `i.reddit.com`, `Sec-Fetch-Dest: image` | 403, boş gövde |
| `Sec-Purpose: prefetch;prerender` | 403 |
| Düz HTTP `old.reddit.com`, yalnızca `Accept: text/html` | 302 |
| Yasaklı olmayan host (`CONNECT localhost:9443`) | TLS açılmadı; istemci sunucunun kendi sertifikasını gördü |
| `CONNECT localhost:9443` + SNI `www.reddit.com` | TLS açılmadı (karar SNI'dan değil CONNECT hedefinden) |
| Yasaklı host, istek belgesi | Yasaklı sunucuya bağlantı açılmadı (log'da `server connect` yok) |
| Yasaklı tünelde HTTP olmayan veri | İlk denemede mitmproxy ham TCP'ye düşüp **reddit'e bağlandı**. `rawtcp=false` ile düzeltildi; artık bağlantı kapanıyor, sunucuya gidilmiyor |
| mitmdump varsayılan çıktısı | Tam URL (yol dahil) yazıyordu. `flow_detail=0` ile yalnızca host kalıyor |
| 77.000 girdili PAC (gerçekçi rastgele adlar) | 1,76 MB. Node.js/V8'de ayrıştırma ~55 ms, `FindProxyForURL` çağrısı başına ~0,5 µs |
| `stopgoon_pac_padding=77000` ile sunulan PAC | 2,0 MB, yerel indirme ~10 ms |

**mitmproxy API doğrulaması (kurulu 12.2.3 kaynağından):**

- `tls_clienthello(data: tls.ClientHelloData)`; `data.ignore_connection = True` TLS'i açmadan geçirir.
- `CONNECT` hedefi: `data.context.server.address`. `mitmproxy/proxy/layers/http/__init__.py` içindeki `handle_connect`, `CONNECT` isteğinin host/port'unu buraya yazar. SNI ayrı bir alandır (`data.client_hello.sni`, `context.client.sni`) ve kullanılmaz.
- Varsayılan `connection_strategy=eager` iken mitmproxy `CONNECT` alır almaz hedef sunucuya bağlanır ve TLS'i önce sunucuyla kurar (`addons/tlsconfig.py`). Bu yüzden addon `lazy` ayarlar.
- `requestheaders(flow)` içinde `flow.response` atanırsa istek sunucuya gitmez. `http.Response.make(status_code, content, headers)`.
- `running` ve `done` kancaları mevcut. `mitmproxy.tools.main.mitmdump(args=None)` mevcut (Aşama 3'te kullanılacak).

### Windows'ta elle doğrulanacaklar (§19 Aşama 1)

Her tarayıcıyı ayar değişikliğinden sonra tamamen kapatıp yeniden aç. Sonuçları aşağıya yaz.

| # | Soru | Nasıl | Chrome | Edge | Firefox |
|---|---|---|---|---|---|
| 1 | PAC okunuyor mu? | `reddit.com` aç; mitmdump konsolunda `redirected reddit.com` görünmeli. Chrome/Edge: `chrome://net-internals/#proxy` / `edge://net-internals/#proxy` PAC adresini göstermeli | | | |
| 2 | Aynı sekmede 302 çalışıyor mu? Adres çubuğu ne gösteriyor? | Adres çubuğuna `reddit.com` yaz, Enter. Beklenen: aynı sekmede video, adres çubuğunda YouTube adresi | | | |
| 3 | `Sec-Fetch-Dest` / `Sec-Purpose` beklendiği gibi mi? | Geliştirici Araçları → Ağ. Gezinmede `Sec-Fetch-Dest: document`; adres çubuğunda yazarken ön yükleme varsa `Sec-Purpose: prefetch` | | | |
| 4 | `CONNECT` hedefine erişim | Linux'ta doğrulandı (yukarıda). Windows'ta ek iş yok | — | — | — |
| 5 | ~2 MB PAC yükleme/değerlendirme süresi | `--set stopgoon_pac_padding=77000` ile başlat, tarayıcıyı yeniden aç. Normal gezinmede gecikme hissediliyor mu? Ölçüm için: `chrome://net-export` kaydı (PAC indirme ve proxy çözümleme olayları) | | | |
| 6 | `?v=` değişince PAC yeniden okunuyor mu? | Proxy'yi padding'siz başlat, `reddit.com`'u dene. Sonra proxy'yi padding'li yeniden başlat, `winsys set 2` çalıştır, tarayıcıyı **kapatmadan** `net-internals/#proxy` adresini ve PAC boyutunu kontrol et | | | |
| 7 | Firefox kök sertifikaya güveniyor mu? | Firefox'ta `reddit.com`: sertifika hatası yoksa güveniyor. Hata varsa `about:config` → `security.enterprise_roots.enabled` değerini kontrol et, `true` yap, yeniden dene | — | — | |
| 8 | Stop Goon kapalıyken ne oluyor? | mitmdump'ı Ctrl+C ile durdur. (a) `reddit.com` → beklenen: bağlantı hatası. (b) `wikipedia.org` → beklenen: normal. (c) Tarayıcıyı yeniden aç ve (a)/(b)'yi tekrarla (PAC indirilemediğinde doğrudan bağlantıya düşüyor mu?) | | | |

Ek olarak kontrol et: `reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"` çıktısında `ProxyEnable` ve `ProxyServer` değerleri, `winsys set` öncesiyle aynı olmalı.

### Aşama 1 temizliği

```bat
.venv\Scripts\python -m stopgoon.winsys clear
certutil -user -delstore Root mitmproxy
rmdir /s /q "%LocalAppData%\StopGoon\mitmproxy"
```
