---
title: Gizlilik ve yerel hafıza sınırı
type: working-guide
authority: non-canonical
---

# Gizlilik ve yerel hafıza sınırı

> [!warning] Gizli bilgiyi paylaşma
> Parola, erişim anahtarı, belirteç, `.env` içeriği, kimlik bilgisi veya özel
> veri Codex/Claude sohbetine, web aracına, eklentiye, loga ya da Obsidian
> notuna yazılmaz.

## Yerel hafıza ne yapar?

- Yalnızca yerel makinede çalışır; ağ isteği yapmaz.
- Python kaynaklarından yalnızca dosya karması, sembol adı ve import/bağımlılık
  ilişkisi üretir; kaynak metnini, değişken değerini veya gizli bilgiyi notlara
  kopyalamaz.
- `secrets`, `.secrets`, `credentials` ve `private` adlı yol bileşenlerini
  bütünüyle kapsam dışı bırakır.
- Çıktılar `var/memory/` ve `docs/hafiza/.generated/` altında yerel ve git dışı
  kalır.

## Agent çalışma kuralı

Gizli bilgi gerektiren bir işlem varsa agent durur ve kullanıcıdan açık yönlendirme
ister. Bu koruma, kullanıcı bir sırrı doğrudan sohbet mesajına yapıştırırsa onu
geri alınabilir kılmaz; bu yüzden sırları sohbet alanına hiç koymamak gerekir.
