// Read current Headway-Demo quote and trade sessions without sending orders.
#property copyright "Gold Intelligence AI contributors"
#property version "1.00"

bool WriteSessions(const int file, const string kind)
{
   for(int day = SUNDAY; day <= SATURDAY; day++)
   {
      for(uint index = 0; index < 64; index++)
      {
         datetime from = 0, to = 0;
         ResetLastError();
         bool found = kind == "quote"
            ? SymbolInfoSessionQuote("XAUUSD", (ENUM_DAY_OF_WEEK)day, index, from, to)
            : SymbolInfoSessionTrade("XAUUSD", (ENUM_DAY_OF_WEEK)day, index, from, to);
         if(!found)
         {
            FileWrite(file, "end_of_day", kind, day, index, "", "", GetLastError());
            break;
         }
         FileWrite(file, "session", kind, day, index, (long)from, (long)to, 0);
         if(index == 63)
            return false;
      }
   }
   return true;
}

void OnStart()
{
   const string output = "gold_headway_xauusd_sessions.csv";
   for(int i = 0; i < 80 && !IsStopped(); i++)
   {
      if(TerminalInfoInteger(TERMINAL_CONNECTED) && AccountInfoString(ACCOUNT_SERVER) == "Headway-Demo"
         && SymbolSelect("XAUUSD", true) && SymbolIsSynchronized("XAUUSD"))
         break;
      Sleep(250);
   }
   if(IsStopped() || !TerminalInfoInteger(TERMINAL_CONNECTED)
      || AccountInfoString(ACCOUNT_SERVER) != "Headway-Demo" || !SymbolIsSynchronized("XAUUSD"))
   {
      Print("Headway session export: synchronized Headway-Demo XAUUSD unavailable");
      return;
   }
   if(FileIsExist(output))
   {
      Print("Headway session export: existing output retained");
      return;
   }
   int file = FileOpen(output, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(file == INVALID_HANDLE)
   {
      Print("Headway session export: FileOpen error ", GetLastError());
      return;
   }
   FileWrite(file, "record", "kind", "weekday_sunday_zero", "index",
      "from_raw", "to_raw", "mt5_error");
   FileWrite(file, "snapshot", "Headway-Demo/XAUUSD", "", "", (long)TimeTradeServer(), (long)TimeGMT(), 0);
   if(WriteSessions(file, "quote") && WriteSessions(file, "trade"))
      FileWrite(file, "complete", "", "", "", "", "", 0);
   FileClose(file);
}
