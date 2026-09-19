MARKETHQ DATE RESOLVER - TEK SEFERLIK FIX

1) Bu klasoru MarketHQ proje kokune kopyala.
2) PowerShell ac.
3) MarketHQ kokunde calistir:

   powershell -ExecutionPolicy Bypass -File .\date-resolver-fix-bundle\apply-date-resolver-fix.ps1

Script sunlari yapar:
- research-date-resolver-agent-v1.ts dosyasini dogru/fixed surumle degistirir.
- experiment-generator-agent-v4-date-resolver.ts dosyasini fixed surumle degistirir.
- AgentId union'a research-date-resolver ekler.
- Registry'ye resolver dependency kaydini ekler.
- experiment-generator icin resolver dependency ekler.
- register-agents.ts icine import + registration ekler.
- Islem oncesi backup klasoru olusturur.

Sonra:

   cd frontend
   npm run build

Beklenen: TS2345 (research-date-resolver AgentId degil), TS7053 (indexleme), TS2339 (lookbackBars/trainBars/validationBars/independentBars) hatalari kalkmali.
