Kamu membantu mengisi data merchant dari teks mentah. Baca TEKS di bawah, lalu usulkan nilai untuk field yang BENAR-BENAR disebut di teks.

## Format jawaban

Jawab HANYA dengan satu objek JSON, tanpa teks lain, tanpa penjelasan:

{"candidates": [{"path": "...", "value": "...", "evidence": "..."}]}

- `path`: salah satu path dari DAFTAR FIELD di bawah, persis seperti tertulis.
- `value`: nilai yang diusulkan, sebagai teks.
- `evidence`: kutipan PERSIS dari TEKS (salin kata demi kata, bukan parafrase, bukan terjemahan) yang menjadi dasar nilai itu. Maksimal 200 karakter.
- Satu usulan untuk satu field. Jika tidak ada yang bisa diusulkan, jawab `{"candidates": []}`.

## Aturan

1. Jangan mengisi field yang tidak ada di teks. Lebih baik kosong daripada menebak.
2. `evidence` harus muncul persis di TEKS. Usulan tanpa kutipan yang cocok akan ditolak oleh program.
3. Untuk sole proprietorship: nama pemilik tidak boleh dijadikan nama usaha, kecuali teks menyebutnya sebagai nama usaha.
4. Tanggal yang ambigu (misalnya 06/02/2004, bisa 6 Februari atau 2 Juni) ditulis apa adanya dan diberi `"ambiguous": true`, contoh: {"path": "...", "value": "06/02/2004", "evidence": "...", "ambiguous": true}.
5. Teks bertanda [DISAMARKAN] berisi data yang sengaja disembunyikan. Jangan menebak isinya.
6. Hanya gunakan path dari DAFTAR FIELD. Jangan menambah path lain. Data sensitif (nomor jaminan sosial, SIM, paspor, rekening) tidak ada di daftar dan tidak boleh muncul di jawaban.

## DAFTAR FIELD (path — format nilai)

{{ALLOWED_FIELDS}}

## TEKS

{{TEXT}}
