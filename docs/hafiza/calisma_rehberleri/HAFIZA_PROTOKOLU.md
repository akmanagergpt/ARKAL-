---
title: ARKALI Hafıza Protokolü
type: operating-guide
status: active
authority: non-canonical
---

# ARKALI Hafıza Protokolü

## Yetki modeli

1. Repository içindeki canonical belgeler, kaynak kod ve kabul kanıtları otoritedir.
2. `docs/hafiza/` yalnız insan görünümü, açıklama ve bağlantı katmanıdır.
3. Faz, gereksinim, ADR, bulgu veya karar kayıtları burada ikinci kez tutulmaz.
4. Hafıza ile kaynak çelişirse kaynak kazanır; çelişki **HAFIZA SAPMASI / MEMORY_DRIFT** olarak raporlanır.

## Göreve başlama

1. Repository kimliği, branch ve çalışma ağacı doğrulanır.
2. [[ARKALI_HANDOFF]] ve görevin gerektirdiği canonical belgeler okunur.
3. Önce özellik sahibi dosyalar, doğrudan bağımlılıklar ve testler incelenir.
4. Kanıt yetersizse ters bağımlılıklar, API/arayüz bağlantıları ve ilgili bounded context açılır.
5. Kabul, güvenlik veya mimari kapı gerekiyorsa geniş doğrulama yapılır.

## Not oluşturma

- Her kaynak dosya için Markdown kartı oluşturma.
- Canonical metni kopyalama; doğrudan bağla.
- Kararlı bileşen/özellik bilgilerini kısa tut.
- Geçici ve ayrıntılı ilişki verilerini `var/memory/` altında yeniden üretilebilir biçimde sakla.
- Bir notun doğruluğunu yalnız HEAD ile değil, bağlı kaynakların içerik hash'leriyle ilişkilendir.

## Paket 1 sınırı

Bu ilk kurulum yalnız Obsidian insan görünümünü sağlar. Üretim API'si, `/memory/*` uç noktası, CLI komutu, kod grafiği değişikliği veya görev bağlam derleyicisi içermez.

[[docs/hafiza/ANA_SAYFA|Ana sayfaya dön]]
