# Atlas Trade

Atlas Trade, Binance USDⓈ-M Futures verisini kendisi alan, likit pariteleri tarayan,
trend + momentum + volatilite filtresi kullanan ve pozisyon riskini otomatik
hesaplayan bir işlem botudur. Yanında Türkçe, yerel bir kontrol paneli bulunur.

> Hiçbir strateji kâr garantisi vermez. Varsayılan kurulum gerçek para kullanmaz.

## En kolay kullanım

İlk kurulumda Python 3.12 veya üzeri ve Node.js 22.13 veya üzeri gerekir.
Proje klasöründe aşağıdaki komutlarla bağımlılıkları kurun:

```powershell
python -m pip install "fastapi>=0.115,<1" "uvicorn>=0.34,<1"
npm ci
Copy-Item .env.example .env
```

Paper modunda API anahtarı gerekmez. Gerekirse anahtarları yalnızca yerel
`.env` dosyasına yazın. `.env`, özel anahtarlar, günlükler ve `runtime/`
altındaki hesap/işlem verileri GitHub'a eklenmez. `.env.example` boş anahtar
alanları içeren paylaşılabilir şablondur.

Proje klasöründeki **Atlas-Trade-Baslat.cmd** dosyasına çift tıklayın. Bot ve
dashboard arka planda açılır; tarayıcı otomatik olarak gelir.

Kapatmak için **Atlas-Trade-Durdur.cmd** dosyasına çift tıklayın. Bu işlem yeni
işlem açılmasını durdurur ve yerel programları kapatır. Gerçek/testnet Binance
modunda borsaya daha önce yazılmış stop ve kâr alma emirleri korunur.

## Varsayılan güvenli mod

- Mod: `paper`
- Başlangıç bakiyesi: 100 USDT
- Veri: gerçek Binance Futures piyasa verisi
- Emirler: yalnızca yerel sanal hesapta
- Evren: 24 saatlik hacmi en az 25 milyon USDT olan en likit 30 USDT perpetual
- Analiz mumları: 15 dakika giriş + 1 saat trend onayı; yalnızca tamamen kapanmış mumlar
- Tarama sıklığı: 15 dakika
- Risk: işlem başına %0,5
- İşlem başına azami risk: %2
- Günlük zarar kilidi: %10
- Kırılım penceresi: son 12 adet 15 dakikalık mum (yaklaşık 3 saat)
- Giriş filtresi: ADX, hacim, RSI ve minimum oynaklık doğrulaması
- Üç RSI: 7/14/21 dönemleri 15 dk ve 1 saat için hesaplanır. 15 dk üçlüsü, RSI 14 bandı ve hızlı RSI yönüyle birlikte tek analiz oyu üretir; diğer analizlerin onayı varsa RSI tek başına veto değildir. RSI'lar bağımsız sinyaller değildir; kâr avantajı kanıtlanmış değildir.
- Kaldıraç: 10x
- Marjin modu: isolated
- Ana teminat: sinyal kalitesine göre 5–40 USDT
- Normal açık pozisyon sınırı: 4. Seçilen LONG/SHORT yönünde 7–9 analiz onayı olan adaylar bu sınır doluyken de açılabilir; 7+ adaylar için ayrıca bir adet tavanı yoktur.
- İstisna yalnızca pozisyon sayısı içindir. Aynı paritede ikinci pozisyon, aynı mumun tekrar emri, duraklatma, günlük zarar, işlem riski ve emir defteri kontrolleri aşılmaz. Her emirden önce güncel boş teminat ve giriş komisyonu kontrol edilir; paper aracı da yetersiz bakiyeyi reddeder.

Bu değerler [config.toml](./config.toml) içinden değiştirilebilir. `symbols = []`
dinamik tüm-coin taramasıdır. Belirli coinlerle sınırlamak için örneğin
`symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]` yazın.

## Strateji

İşlem adayları panelinde parite seçince, analize giren son 60 kapanmış Binance mumu
küçük grafikte gösterilir. Aktif FVG bölgeleri ve MSS seviyeleri aynı analizden gelir.
Sarı çizgi taslak giriş/analiz fiyatıdır; aday varsa stop ve 1:2 hedef de çizilir.
Bu çizgiler gerçekleşmiş emir değildir; dolum fiyatı ve yuvarlama son seviyeleri değiştirebilir.
Grafik seçilen parite için Binance USD-M WebSocket mum akışıyla güncellenir.
Henüz kapanmamış mum ve mavi canlı fiyat çizgisi yalnızca gösterim içindir; botun
kapalı mum analizi, FVG/MSS ve taslak seviyeleri bu akışla değiştirilmez.
Bağlantı kesilirse canlı etiketi kapanır; artan beklemeyle yeniden bağlanılır ve
son 60 mum REST geçmişinden tamamlanır. Parite değişiminde eski bağlantı kapatılır.
Kaynak: [Binance Kline Streams](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market).

Sabit mum kırılımı ve tüm koşulların birlikte sağlanması zorunluluğu kaldırıldı.
Aktif giriş kuralı: **9 analizin en az 4'ü** onay vermeli. LONG ve SHORT ayrı sayılır;
eşiği geçen daha yüksek sayılı yön aday olur, eşitlikte WAIT. 1 saat onayı,
RSI, MSS veya FVG tek başına zorunlu değildir.

Oylar: 15 dk fiyat/EMA20 yönü + momentum (tek oy), 1 saat EMA trendi,
RSI 7/14/21 + RSI 14 bandı (tek oy), MSS, likidite süpürmesi, FVG dönüş tepkisi,
ADX, hacim ve oynaklık. Son üçü yön belirtmeyen ortak piyasa koşullarıdır.
Eksik üst zaman verisine onay verilmez. Emir defteri güvenliği oylamaya dahil değildir.

Minimum 4 onayda teminat puanı 85'ten başlar; onay sayısı arttıkça 100'e ve
5–40 USDT hedef teminata yükselir. Bu bir başarı olasılığı değildir.
Eski `minimum_signal_score` artık yalnızca teminat ölçeğinin tabanıdır; ek giriş eşiği değildir.
Geçersiz fiyat/ATR, kapalı mum/veri yeterliliği, günlük zarar, risk, bakiye,
açık pozisyon ve emir defteri güvenliği şartları değişmez.

Aşağıdaki birleşik yapılar ayrıca gösterilir; artık zorunlu giriş kalıbı değildir:
- **Süpürme → MSS:** iki yandan ikişer kapanmış mumla teyit edilmiş salınım seviyesinin en az 0,05 ATR aşılması ve geri alınması; ardından en fazla 6 mum içinde MSS.
- **MSS → FVG dönüşü:** yakın tarihli MSS çevresinde oluşan üç mumluk fiyat boşluğuna geri dönüş ve bölgenin dışına yönlü kapanış. Boşluk en az 0,1 ATR, orta mum gövdesi en az 0,5 ATR olmalı. Tamamen dolmuş bölgeler tekrar kullanılmaz.
- MSS, yukarı yönde önceki daha düşük tepenin; aşağı yönde önceki daha yüksek dibin en az 0,5 ATR gövdeli kapanışla aşılmasıdır. Sadece fitil yeterli değildir. Onay sinyal mumu dahil 4 mum geçerlidir; kırılan seviye kapanışla korunmalıdır.
- Salınımlar en fazla 80 mumluk geçmişten, FVG'ler 40 mumdan aranır. Bunlar veri ufkudur; mumların tek yönde olması veya bu pencerenin en yüksek/düşük fiyatının kırılması gerekmez.
- FVG dönüş tepkisi MSS'den bağımsız bir oy verir; birleşik FVG/MSS etiketi için yakın tarihli MSS ayrıca aranır. Birleşik yapı yoksa ATR stopu kullanılır.
- Stop mesafesi, 2,2 ATR ile kurulumun geçersizlik seviyesinin 0,15 ATR ötesinden daha geniş olanıdır. 1:2 hedef/zarar, 10x isolated, %2 işlem riski, günlük %10 zarar sınırı ve 5–40 USDT teminat korunur. Teminat risk sınırına sığmıyorsa giriş yoktur.

### Emir defteri likiditesi

Adaylarda ve emirden hemen önce Binance USD-M public `/fapi/v1/depth?limit=100` anlık görüntüsü kontrol edilir:
- En fazla %0,08 alış-satış farkı, %0,05 tahmini kayma.
- Orta fiyatın ±%0,2 bandında her iki tarafta en az 10.000 USDT ve planlanan işlem büyüklüğünün 20 katı görünür derinlik.
- Sinyal fiyatından en fazla 0,5 ATR uzaklaşma; 10 saniyeden eski veya 5 saniyeden fazla gelecekte görünen veri reddedilir.
- Veri alınamazsa giriş engellenir; mum analizi tek başına emir gönderemez.
Bu eşikler başlangıç parametreleridir; kâr avantajları doğrulanmış değildir. Emir defteri değişebilir; görünür emirler gerçekleşme garantisi veya yön tahmini değildir. Grafik süpürmeleri gizli stop/tasfiye emirlerini göstermez.
Kaynak: [Binance Order Book API](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book).

## Binance Futures Testnet hesabı bağlama

API anahtarını sohbet mesajına yazmayın. Proje klasöründe `.env.example`
dosyasının kopyasını `.env` adıyla oluşturup yalnızca kendi bilgisayarınızda
doldurun:

```text
BINANCE_API_KEY=TESTNET_ANAHTARINIZ
BINANCE_API_SECRET=TESTNET_GIZLI_ANAHTARINIZ
ATLAS_MODE=testnet
ATLAS_DRY_RUN=false
```

Ardından Atlas Trade'ı kapatıp yeniden başlatın. Testnet emirleri Binance Futures
test ortamına gider; paper hesabındaki 100 USDT bakiyeden ayrıdır.

## Gerçek Binance hesabı

Canlı mod kodda desteklenir ancak paper ve testnet sonuçları yeterli görülmeden
açılmamalıdır. API anahtarında yalnızca Futures işlem yetkisi verin, para çekme
yetkisini kapatın ve mümkünse IP kısıtı kullanın. Canlı mod için üç ayrı kilidin
birlikte açılması gerekir:

```text
ATLAS_MODE=live
ATLAS_DRY_RUN=false
ATLAS_ALLOW_LIVE=I_UNDERSTAND_THE_RISK
```

## Geçmiş veri testi

```powershell
python -m bot.backtest --symbol BTCUSDT --days 90
```

Test bir paritede aynı anda tek pozisyon taşır, sinyal mumundan sonraki mumda
girer, komisyon ve ihtiyatlı fiyat kaymasını hesaba katar. Sonuçlar işlem sayısı,
kazanma oranı, net getiri, kâr faktörü ve maksimum düşüşü gösterir. Fonlama ve
likidasyon etkileri ayrıca değerlendirilmeden canlıya geçilmemelidir. Geçmiş mum testinde tarihsel emir defteri bulunmadığından likidite kilidi test edilmez; çıktı yalnızca mum stratejisinin sonucudur, tam bot performansı değildir.

## Geliştirici kontrolleri

```powershell
python -m unittest discover -s tests -v
npm run build
npm audit --omit=dev
```

Bot çekirdeğindeki `Broker` arayüzü daha sonra MetaTrader 5 veya başka bir forex
sağlayıcısı eklenebilecek şekilde ayrılmıştır.
