# ARKALI GENESIS v2 — YENİ SOHBET / OTURUM DEVAM NOTU

Bu not, ChatGPT veya Claude konuşma sınırına ulaşıldığında ARKALI geliştirmesine güvenli biçimde devam etmek için hazırlanmıştır.

## Temel Kural

Sohbet geçmişi ana hafıza değildir. Ana gerçek kaynak Git repository, ARKALI_HANDOFF.md, BUILD_STATE.md, PHASE_HISTORY.md, REQUIREMENT_REGISTER.md, AUTHORITY_MAP.yaml, HUMAN_GATE_RECORDS.md, kabul edilmiş ADR ve evidence kayıtlarıdır.

## Claude Code'da yeni oturuma geçerken

1. Mevcut işi tamamen bitmesini bekle.
2. Working tree'nin temiz olduğundan emin ol.
3. ARKALI_HANDOFF.md güncel olmalı.
4. Claude Code'da yeni session aç.
5. Aynı repository kökünü seç: C:\Users\lenovo\Desktop\ARKALI
6. ARKALI_NEW_SESSION_PROMPT.txt içeriğini Claude'a gönder.
7. Claude önce ARKALI_HANDOFF.md dosyasını okumalı.
8. scripts/check_handoff.py çalıştırılmalı.
9. HANDOFF_DRIFT varsa geliştirmeyi durdur.
10. Tutarlıysa BUILD_STATE, PHASE_HISTORY ve ilgili canonical belgeleri doğrula.
11. Yalnız NEXT EXACT ACTION noktasından devam et.
12. Mimariyi sıfırdan yeniden tasarlatma.
13. Önceden yapılmış işleri sohbet hafızasına dayanarak tekrar üretme.

## Yeni ChatGPT sohbetine geçerken

1. Yeni sohbet aç.
2. Güncel ARKALI_HANDOFF.md dosyasını yükle.
3. Gerekirse güncel docs klasörünü ZIP yapıp yükle.
4. Kod incelemesi gerekiyorsa ilgili scripts veya repository parçalarını da yükle.
5. ARKALI_NEW_SESSION_PROMPT.txt içeriğini gönder.
6. Şunu belirt: "Repository ve ARKALI_HANDOFF.md otoritedir. Eski sohbet hafızasına dayanma."
7. Yeni ChatGPT handoff ile repository belgelerini karşılaştırmalı.
8. Tutarsızlık varsa HANDOFF_DRIFT olarak durmalı.
9. Tutarlıysa NEXT EXACT ACTION'dan devam etmeli.
10. Önceki fazları sıfırdan tekrar açmamalı.

## Kritik devam dosyaları

- ARKALI_HANDOFF.md
- ARKALI_NEW_SESSION_PROMPT.txt
- docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md
- docs/CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md
- docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md
- docs/ARKALI_GENESIS_V2_START_COMMAND.txt
- docs/canonical/REQUIREMENT_REGISTER.md
- docs/canonical/AUTHORITY_MAP.yaml
- docs/build/BUILD_STATE.md
- docs/build/PHASE_HISTORY.md
- docs/build/OPEN_BLOCKERS.md
- docs/build/KNOWN_FAILURES.md
- docs/build/DECISION_LOG.md
- docs/acceptance/EVIDENCE_INDEX.md
- docs/acceptance/HUMAN_GATE_RECORDS.md
- docs/adr/ADR_INDEX.md

## Handoff ne zaman güncellenmeli?

ARKALI_HANDOFF.md şu durumlarda yenilenmeli:
- her machine-accepted phase sonrası
- her Human Gate kararı sonrası
- accepted governance erratum sonrası
- Stable Core promotion sonrası
- rollback sonrası
- NEXT EXACT ACTION değiştiğinde
- yeni BLOCKER/HIGH continuation stratejisini değiştiriyorsa

Handoff ikinci bir canonical authority değildir. Çelişki varsa authoritative repository artifact kazanır.

## Yeni oturumda kontrol listesi

1. Repository root doğru mu?
2. Branch doğru mu?
3. HEAD handoff ile uyumlu mu?
4. Working tree temiz mi?
5. Requirement sayıları doğru mu?
6. Accepted/unlocked phase durumu doğru mu?
7. Human Gate durumu doğru mu?
8. ADR durumları doğru mu?
9. BLOCKER/HIGH sayıları doğru mu?
10. NEXT EXACT ACTION gerçekten unlocked phase'e mi gidiyor?
11. scripts/check_handoff.py PASS veriyor mu?

Tutarsızlık varsa: HANDOFF_DRIFT.

## ChatGPT'ye kısa devam cümlesi

"Bu ARKALI GENESIS v2 geliştirmesinin devamıdır. Yüklediğim ARKALI_HANDOFF.md ve repository belgeleri mevcut durumun otoritesidir. Önce handoff'u repository kanıtıyla doğrula. Tutarsızlık varsa HANDOFF_DRIFT olarak dur. Tutarlıysa yalnız NEXT EXACT ACTION noktasından devam et. Mimariyi sıfırdan yeniden kurma ve geçmiş işleri sohbet hafızasına dayanarak varsayma."

## Claude'a kısa devam cümlesi

"Open the current ARKALI repository. Read ARKALI_HANDOFF.md first. Verify it against Git, BUILD_STATE, HUMAN_GATE_RECORDS, REQUIREMENT_REGISTER and AUTHORITY_MAP. Run scripts/check_handoff.py. If drift exists, stop with HANDOFF_DRIFT. If consistent, continue only from NEXT EXACT ACTION. Do not restart architecture from scratch and do not rely on previous chat memory."

## Şu anki referans durumu

Bu not oluşturulduğunda:
- Phase 0A: ACCEPTED
- Phase 0B: ACCEPTED
- Human Gate 1: ACCEPTED
- Phase 1: MACHINE-ACCEPTED
- Phase 2: MACHINE-ACCEPTED
- Phase 3: UNLOCKED / NOT_STARTED
- Handoff version: ARKALI-HANDOFF-V1
- Current reference HEAD: 74a9ccfef5e0befdefd8aad52fbf5e3898650c0c
- Next exact action: Phase 3 — Formal State Machines + Capability Graph Schema

Bu bölüm zamanla eskiyebilir. Yeni oturumda her zaman gerçek repository ve ARKALI_HANDOFF.md üzerinden yeniden doğrula.

## En önemli kural

Sohbet biterse proje bitmez.

Yeni AI repository'yi açar, handoff'u doğrular, gerçek Git ve governance durumunu okur ve NEXT EXACT ACTION'dan devam eder.

ARKALI'nın geliştirme hafızası sohbet değil, repository'dir.
