#!/bin/bash
echo "Değişiklikler paketleniyor..."
git add .
git commit -m "Auto-sync: Spark güncellemeleri otomatik aktarıldı"
git push origin main
echo "İşlem tamam! Kodlar başarıyla GitHub'a aktarıldı."
