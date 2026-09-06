# ARKALI çalışma bağlamı

Bu depo, karar ve kabul geçitleri olan yönetişimli bir yazılım fabrikasıdır.
Yalnızca gerekli bağlamı oku; önce `docs/hafiza/.generated/DEVAM_ET.md`, sonra
`var/memory/status.json` varsa onu, ardından işin otoriter belgesini kullan. Eksik bağlamda
`scripts/arkali_memory.py impact <dosya>` çalıştırıp yalnızca ilgili kaynakları
genişlet.

Geri dönüş ve geliştirme akışının insan-okunur açıklaması
`docs/hafiza/calisma_rehberleri/DEVAM_SURECI.md` dosyasındadır. Bu akışı izle;
herhangi bir özet, kaynak veya kabul kaydıyla çelişirse otoriter kaynak kazanır.

Kurallar:

- Gizli bilgileri (`.env`, anahtarlar, parolalar, erişim belirteçleri,
  kimlik bilgileri, özel müşteri/veri dosyaları) açma, isteme, sohbete ekleme,
  haricî araca gönderme veya log/kanıt/not içine yazma. Bir iş bunları gerçekten
  gerektiriyorsa dur ve kullanıcıdan yalnızca gerekli yetkiyi iste.
- Web araması, bulut servisi, eklenti veya uzaktan model çağrısı için proje
  içeriğini paylaşma. Yerel analizde de hassas yol ve dosyalar kapsam dışıdır.
- `docs/canonical/`, kabul kayıtları ve kaynak kod otoritedir. `var/memory/` ve
  `docs/hafiza/.generated/` türetilmiştir; karar vermek için tek başına
  kullanılamaz.
- Hafıza çıktısını yeniden üret; kopya kanonik belge, dosya-başına not veya
  elle düzenlenmiş bağımlılık envanteri oluşturma.
- Grafik yalnızca doğrulanmış Python sembol, import ve bağımlılık ilişkilerini
  kapsar. Kapsanmayan ilişki türlerini boş ya da tamamlanmış gösterme.
- Bir değişiklikten önce güncel handoff, açık bulgular ve geçit durumunu kontrol
  et. Yetki veya kabul geçidi gerektiren işlemleri atlama.
- İş bittiğinde `scripts/arkali_memory.py refresh` ile yerel hafızayı yenile.
