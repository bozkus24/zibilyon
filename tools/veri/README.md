# Zibilyon veri hattı

Her günlük soru için kabul edilebilir cevapları toplar, her cevaba nadirlik katmanı
atar ve sunucunun kullandığı şifreli kataloğu üretir. Hedef ölçüt:

> Bu soru 30 saniyede rastgele bir Türk yetişkine sorulsa, bu cevabı verme olasılığı nedir?

Tek bir kaynak bunu ölçmez. Birden çok sinyal harmanlanır, son kararı insan editör verir.
Gerçek anket verisi geldiğinde ağırlıklar ona göre kalibre edilir.

## Gizlilik düzeni

| Yer | İçerik | Git |
|---|---|---|
| `tools/veri/` | hat kodu, testler, şema örneği | evet |
| `.server-private/zibilyon/sorular/` | gerçek soru tanımları | **hayır** |
| `.server-private/zibilyon/ham/` | Wikidata, görüntülenme ve LLM önbelleği (tarih + sorgu metniyle) | **hayır** |
| `.server-private/zibilyon/editor/` | inceleme sayfaları, `override.csv`, `ekle.csv` | **hayır** |
| `.server-private/zibilyon/cikti/` | aday, sinyal ve katman çıktıları, `katalog.json` | **hayır** |
| `server/catalog.enc` | şifreli katalog (AES-256-GCM) | evet, yalnız şifreli |

Cevap tabloları tarayıcıya gönderilmez ve depoya düz metin olarak girmez.

## Kurulum ve çalıştırma

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r tools/veri/requirements.txt
cd tools/veri
python -m zibilyon_veri hepsi            # topla + sinyal + harman + rapor + katalog
python -m zibilyon_veri takvim
node ../catalog.mjs encrypt              # .env içindeki TRPUZZLE_SERVER_KEY ile
```

Aşamalar tek tek de çalışır: `topla`, `istem`, `sinyal`, `harman`, `rapor`, `katalog`,
`anket`, `kalibre`, `takvim`, `pv60` (görüntülenme ön belleği), `pv12` (12 aylık REST ön belleği).
`--tazele` önbelleği yok sayar.

## Aşamalar

1. **Aday havuzu.** Kaynaklar:
   - Wikidata SPARQL (P31/P279*, Türkçe etiket ve takma ad, trwiki başlığı, sitelink).
   - `llm` etiketli adaylar: kullanıcı Ek A'sı ve beyin fırtınası.
   - Editör ekleri (`editor/ekle.csv`).

   Ardından şu temizlik uygulanır:
   - Türkçe etiketi olmayanlar "etiketsiz" listesine gider.
   - Çeşit gürültüsü atılır ("Amasya elması").
   - `haric_p31` ve `haric_desen` filtreleri uygulanır.
   - `llm` etiketli uygunluk değerlendirmesi uygulanır (`hayir` olanlar elenir, editör geri alabilir).
   - Kırmızı liste uygulanır.
   - Kopya birleştirme yapılır: sunucunun eşleştiricisinin a-c adımlarıyla aynı yere düşen adlar tek cevaptır.
     Wikidata altLabel'ları birleştirmede kullanılmaz (güvenilmez); yalnız eşleştirmede takma ad olur
     ve hiçbir zaman başka bir cevabın asıl adını ezemez.
2. **Sinyaller.**
   - `S_frek`: `wordfreq.zipf_frequency(ad, 'tr')`. Eş seslilerde kullanılmaz; çok kelimeli adlarda güveni düşüktür.
   - `S_goruntu`: trwiki görüntülenmesi, `log10(1 + min(ortalama, medyan))`.
   - `S_dil`: sitelink sayısı.
   - `S_llm`: 3 koşunun medyanı.
   - `S_anket`: varsa gerçek anket verisi.
3. **Harman.** Her sinyal soru içinde yüzdelik sıraya çevrilir. Ağırlıklar soru tipine göredir;
   eksik sinyalde kalan ağırlıklar yeniden ölçeklenir. Anket verisi varsa
   `nihai = 0.7 × anket + 0.3 × bileşik`.
4. **Katman.**
   - Anket varsa p eşikleri kullanılır (%8 / %3 / %1 / %0,3).
   - Yoksa soru içi kotalar kullanılır (%10 / %15 / %25 / %25 / %25).
   - Kısıtlar: Toprak en çok 8 cevap, her katmanda en az 2 cevap.
   - Elmas yalnız editör onayıyla yayına girer; onaysızlar katalogda Altın'da tavanlanır.
5. **Editör raporu.** `editor/<id>.html`, `editor/<id>.csv`, `editor/rapor.html`.
6. **Katalog.** Derlenmiş eşleştirme tablosu: tam ve katlanmış anahtarlar, red listesi, niteleyiciler
   ve yazım toleransı için sözlük engel listesi (wordfreq ilk 80.000 kelime).

## S_llm protokolü

`istem` komutu her soru için 3 farklı ifade ve 3 farklı karıştırılmış sırayla istem üretir
(`ham/llm/<id>.istem.<k>.txt`). Yanıtlar `ham/llm/<id>.yanit.<k>.json` dosyasına
`{"cevaplar": {ad: kişi}, "diger": kalan}` biçiminde yazılır. Toplamı 100'ü aşan koşu orantılı
küçültülür ve ölçek kaydedilir. Bir adayın koşular arası farkı 10'u aşarsa ya da bir koşuda 0, başka bir
koşuda 5 veya üzerindeyse aday `kararsiz` işaretlenir. LLM çıktıları yalnız `llm` etiketli sinyal ve aday
kaynağıdır; hiçbir zaman ölçülmüş veri gibi raporlanmaz.

## Görüntülenme kaynağı

Hedef, Wikimedia REST API'den son 12 ayın aylık değerleridir. Bu ortamın çıkış IP'si Wikimedia tarafında
sıkı hız sınırına takıldığından (HTTP 429, `Retry-After` 20-40 sn) yedek olarak trwiki Action API
(`prop=pageviews`, son 60 gün) kullanılır. Bir soruda tüm makalelerin 12 aylık verisi önbellekte yoksa,
o sorunun **bütün** adayları için 60 günlük veri kullanılır. Kaynak her soru için raporda yazar.

## Anket

Ankete site dışından en az 30, en çok 100 kişi katılır; soru "Aklına gelen ilk 3 X'i yaz" biçimindedir.
Siteye analitik eklenmez.

- Sonuçlar `ham/anket/<soru-id>.csv` dosyasına konur (şablon: `anket_sablon.csv`).
- `python -m zibilyon_veri anket` cevapları sunucunun eşleştiricisinden geçirir.
- Sıra ağırlıkları: 1. cevap 1, 2. cevap 0,6, 3. cevap 0,4.
- p hesaplanır; listede olmayan cevaplar "yeni aday" olarak raporlanır.
- Anketli en az 30 soru biriktiğinde `kalibre` komutu, ağırlıkları anketle Spearman sıra
  korelasyonunu en üst düzeye çıkaracak şekilde ızgara aramasıyla yeniden hesaplar.

## Normalizasyon (sunucu ve hat aynı kurallar)

`zibilyon_veri/normalize.py` ile `server/eslestir.mjs` aynı kuralları uygular.
İkisi de `ortak/normalize_vektorleri.json` ile test edilir (`pytest tools/veri/testler`,
`node --test tests/*.test.mjs`). Vektörler `python tools/veri/vektor_uret.py` ile üretilir;
beklenen sonuçlar elle yazılmıştır.

## Lisanslar ve atıf

- wordfreq verisi: CC BY-SA 4.0 (Robyn Speer ve katkıcılar).
- Wikidata: CC0.
- Wikimedia görüntülenme verisi: CC0.
