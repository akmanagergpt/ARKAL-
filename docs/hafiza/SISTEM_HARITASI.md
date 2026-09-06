---
title: ARKALI Sistem Haritası
type: system-map
status: seed
authority: non-canonical
---

# ARKALI Sistem Haritası

Bu sayfa ayrıntılı teknik gerçekleri kopyalamadan ARKALI deposunda yön bulmayı sağlar. Kesin bilgi için bağlantılı kaynak dosyalar okunmalıdır.

## Yönetişim ve doğrulama

- [[ARKALI_HANDOFF]] — oturumlar arası devam noktası
- [[docs/canonical/REQUIREMENT_REGISTER]] — gereksinim otoritesi
- [[docs/build/BUILD_STATE]] — build/faz durumu
- [[docs/build/PHASE_HISTORY]] — kabul edilmiş faz geçmişi
- [[docs/build/OPEN_BLOCKERS]] — açık bulgular ve engeller
- [[docs/acceptance/HUMAN_GATE_RECORDS]] — insan yetkilendirmeleri
- [[docs/adr/ADR_INDEX]] — mimari karar kayıtları

## Uygulama alanları

- `backend/arkali/` — Python backend ve alan uygulaması
- `frontend/` — kullanıcı arayüzü
- `src-tauri/` — masaüstü kabuğu
- `scripts/` — doğrulama, üretim ve operasyon girişleri
- `backend/arkali/engineering/codeintel/` — kod ve bağımlılık grafiğinin mevcut sahibi
- `backend/arkali/engineering/agent/` — görev bağlamı üretiminin mevcut sahibi

## Türetilmiş veriler

Yeniden üretilebilir makine dizinleri `var/memory/` altında tutulmalıdır. `var/` zaten Git dışında bırakılmıştır. İnsan notlarına ayrıntılı dosya grafiği kopyalanmamalıdır.

## Genişletme ölçütü

Yeni bir bileşen veya özellik kartı yalnız şu durumda açılır:

- İnsanların düzenli olarak bulması gereken kararlı bir kavramsa,
- Birden fazla kaynak/test/karar arasında gezinme sağlıyorsa,
- Canonical içeriği kopyalamadan anlamlı bağlam sunuyorsa.

