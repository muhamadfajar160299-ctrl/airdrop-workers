# airdrop-workers

Pekerjaan airdrop otomatis yang jalan di GitHub Actions — gratis, tanpa kartu
kredit, tanpa server sendiri. Repo ini **publik** supaya Actions-nya gratis
tanpa batas menit, dan **tidak menyimpan secret apa pun** (tidak ada private
key, tidak ada API key, tidak ada password).

## Yang jalan sekarang

### Free-mint radar (`scripts/radar_screen.py`, tiap 15 menit)

Screening drop NFT/token gratis di BNB Chain dari sumber publik:

- MintRadar (datt.my) — index + label per kontrak
- Boltbook Alphapedia (en/zh) + Alpha Board
- AgenticMint — koleksi open
- Gist feed H-eartbreaker

Aturan: hanya label **hijau** yang jadi kandidat. Kuning/merah di-skip.
Kandidat hijau dicek ringan on-chain (kontraknya beneran ada bytecode).
State yang sudah dicek tersimpan di `state/seen.json` supaya tidak lapor
berulang; hasil run terakhir ada di `findings/latest.json`.

Kalau ada kandidat hijau baru, workflow otomatis bikin **GitHub Issue**
berlabel `radar`. Lux (agen) yang verifikasi penuh on-chain sebelum
melapor ke Larisha — tidak ada mint otomatis dari repo ini.

## Batas yang jujur

- Ini screening + deteksi, bukan eksekusi. Semua keputusan mint tetap di
  tangan Larisha, dan semua transaksi on-chain tetap butuh persetujuan dia.
- GitHub Actions terjadwal bisa telat beberapa menit saat antrean padat.
- Sumber yang butuh login / kena Cloudflare (mis. nftcalendar.io) tidak
  terjangkau dari runner ini.
- Jadwal Actions dimatikan GitHub kalau repo tidak ada aktivitas 60 hari —
  commit state tiap run menjaga repo tetap aktif.
