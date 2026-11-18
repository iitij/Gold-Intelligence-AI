// Read-only export. Bounds are native MT5 numeric timestamp labels.
#property strict
#property script_show_inputs

input datetime FromNative = D'2026.11.12 12:00:00';
input datetime ToNative = D'2026.11.12 12:02:00';

void OnStart()
{
   if (AccountInfoString(ACCOUNT_SERVER) != "Headway-Demo" ||
       _Symbol != "XAUUSD" || FromNative >= ToNative)
   {
      Print("Expected Headway-Demo, XAUUSD and increasing native bounds");
      return;
   }
   MqlTick ticks[];
   ResetLastError();
   int count = CopyTicksRange(_Symbol, ticks, COPY_TICKS_ALL,
                              (ulong)FromNative * 1000, (ulong)ToNative * 1000 - 1);
   int copy_error = GetLastError();
   if (count <= 0 || copy_error != 0)
   {
      PrintFormat("No XAUUSD ticks exported: rows=%d error=%d", count, copy_error);
      return;
   }
   string path = StringFormat("headway_xauusd_ticks_%I64d_%I64d_%I64u.csv",
                              (long)FromNative, (long)ToNative, GetMicrosecondCount());
   int file = FileOpen(path, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if (file == INVALID_HANDLE)
   {
      PrintFormat("FileOpen failed: %d", GetLastError());
      return;
   }
   bool ok = FileWrite(file, "time_msc", "bid", "ask", "flags") > 0;
   for (int i = 0; i < count && ok; i++)
      ok = FileWrite(file, ticks[i].time_msc, DoubleToString(ticks[i].bid, _Digits),
                     DoubleToString(ticks[i].ask, _Digits), ticks[i].flags) > 0;
   FileClose(file);
   if (!ok)
   {
      FileDelete(path, FILE_COMMON);
      Print("Tick CSV write failed");
      return;
   }
   PrintFormat("Exported %d ticks to Common/Files/%s", count, path);
}
