---
title: ARKALI kullanıcı kullanım kılavuzu
type: user-guide
authority: non-canonical
---

# ARKALI kullanıcı kullanım kılavuzu

Bu kılavuz, ARKALI üzerinde yeniden çalışmaya başlamak istediğinde izleyeceğin
en basit yoldur. Teknik ayrıntıları bilmen gerekmez.

## Her geri dönüşte yapacağın şey

1. Obsidian’ı aç ve ARKALI kasasına gir.
2. [[docs/hafiza/.generated/DEVAM_ET|Devam Et]] sayfasını aç.
3. Sayfadaki **Güvenli başlangıç** adımlarını sırayla gözden geçir.
4. Codex veya Claude’a hedefini açıkça söyle.

Örnek:

> ARKALI üzerinde devam etmek istiyorum. Önce `Devam Et` sayfasını, handoff
> kaydını, açık engelleri ve ilgili insan onaylarını incele. Bana nerede
> kaldığımızı, riskleri ve güvenli tek sonraki adımı Türkçe özetle. Kod
> değiştirmeden önce benden onay iste.

## Bir geliştirme istediğinde

İsteğini şu üç parçayla yaz:

1. **Amaç:** Ne değişsin?
2. **Başarı ölçütü:** Bittiğini nasıl anlayacağız?
3. **Sınır:** Neye dokunulmasın?

Örnek:

> Amaç: Komut merkezinde mevcut uygulamayı tanıtma akışını iyileştir.
> Başarı ölçütü: İlgili testler geçsin ve kullanıcı akışı anlaşılır olsun.
> Sınır: İnsan onayı, güvenlik ve mimari geçitlerine dokunma; yeni dış servis
> ekleme.

## Sonucu nasıl kontrol edersin?

AI’den şunları kısa biçimde iste:

- Hangi dosyalar değişti?
- Hangi testler çalıştı ve sonucu ne?
- Açık risk veya blocker var mı?
- Bir sonraki tek adım ne?

Sonra Obsidian’da [[docs/hafiza/.generated/DEVAM_ET|Devam Et]] sayfasını yeniden
aç. Yerel hafıza, Python değişikliklerini otomatik yeniler.

## Bilmen gereken sınırlar

- AI nerede kalındığını bulup öneri verebilir; insan onayı gereken işlemleri
  senin yerine onaylayamaz.
- Python bağımlılıkları otomatik izlenir. Frontend/TypeScript, rota ve veri
  modeli etkileri henüz otomatik analiz edilmez.
- Devir kaydıyla gerçek çalışma durumu çelişirse AI bunu önce görünür kılmalı;
  doğrudan geliştirmeye geçmemeli.

## Gizlilik

Parola, API anahtarı, `.env` içeriği veya özel veri yapıştırma. Ayrıntılar için
[[docs/hafiza/calisma_rehberleri/GIZLILIK|gizlilik rehberini]] oku.
