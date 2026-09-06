---
title: ARKALI geliştirmeye devam etme süreci
type: working-guide
authority: non-canonical
---

# ARKALI geliştirmeye devam etme süreci

Bu rehber, ARKALI’ye bugün ya da aylar sonra yeniden dönerken izlenecek çalışma
sırasıdır. Amaç, önce doğru bağlamı bulmak; sonra yalnızca gerekli kapsamda
değişiklik yapmak; en sonunda kanıtı ve yerel hafızayı güncellemektir.

> [!important] Yetki sınırı
> Bu belge çalışma yolunu açıklar. Gereksinim, mimari karar, kabul kaydı veya
> insan onayı yerine geçmez. Çelişkide ilgili canonical belge kazanır.

## 1. Geri dön

1. Obsidian’da [[docs/hafiza/.generated/DEVAM_ET|Devam Et]] sayfasını aç.
2. [[ARKALI_HANDOFF|Devir kaydını]], [[docs/build/BUILD_STATE|build durumunu]]
   ve [[docs/build/OPEN_BLOCKERS|açık bulguları]] oku.
3. Devir kaydı ile çalışma ağacı veya mimari ölçümler çelişirse bunu **HAFIZA
   SAPMASI / HANDOFF_DRIFT** olarak ele al. Sapmayı görünür kılmadan geliştirmeye
   devam etme.
4. İş insan onayı gerektiriyorsa
   [[docs/acceptance/HUMAN_GATE_RECORDS|insan kapısı kayıtlarını]] kontrol et.

## 2. İşi netleştir

- Hedefi bir cümleyle yaz: “Ne değişecek ve başarı nasıl ölçülecek?”
- Gereksinimi [[docs/canonical/REQUIREMENT_REGISTER|gereksinim kaydında]] bul.
- Karar geçmişini [[docs/build/DECISION_LOG|karar günlüğü]] ve
  [[docs/adr/ADR_INDEX|ADR dizininde]] kontrol et.
- Eksik yetki, belirsiz hedef veya açık blocker varsa kod yazma; önce bunu
  kullanıcıya bildir.

## 3. Dar kapsamla incele

1. Önce yalnızca hedef dosyayı ve doğrudan ilişkili canonical belgeleri aç.
2. Python dosyası için şu sorguyu kullan:

   ```text
   python scripts/arkali_memory.py impact <dosya>
   ```

3. Çıkan kaynakları ve testleri incele; kanıt yetmezse kapsamı kontrollü olarak
   genişlet.
4. `route`, `model` ve `frontend_contract` ilişkilerinin henüz otomatik
   analizde olmadığını unutma; onları tamamlanmış varsayma.

## 4. Değiştir ve doğrula

1. Sadece onaylı hedef için gerekli en küçük değişikliği yap.
2. Etkilenen testleri çalıştır; işin riskine göre ilgili daha geniş doğrulamayı
   da uygula.
3. İlgili kabul kapısı, güvenlik sınırı veya mimari bütçe varsa onu atlama.
4. Bulgu, karar veya kullanıcı onayı oluştuysa onu kendi otoriter kaydına ekle;
   bu rehbere kopyalama.

## 5. Kapat ve devret

1. Yerel hafızayı yenile:

   ```text
   python scripts/arkali_memory.py refresh
   ```

2. [[docs/hafiza/.generated/DEVAM_ET|Devam Et]] sayfasının güncellendiğini
   kontrol et.
3. Bir sonraki kişinin tek cümlede anlayacağı devir bilgisini canonical handoff
   sürecine uygun şekilde yaz.
4. Değişiklik, test sonucu, kalan risk ve **tek sonraki adımı** belirt.

## Gizlilik

[[docs/hafiza/calisma_rehberleri/GIZLILIK|Gizlilik rehberini]] her zaman uygula:
sırları sohbet, not, log veya dış araca koyma. Hassas bilgi gerekliyse dur ve
kullanıcıdan açık yönlendirme iste.
