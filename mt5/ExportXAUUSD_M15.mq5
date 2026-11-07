//+------------------------------------------------------------------+
//| Gold Intelligence AI - XAUUSD M15 closed-bar CSV exporter        |
//| READ-ONLY; no account information or trade/order functions.      |
//+------------------------------------------------------------------+
#property copyright "Gold Intelligence AI contributors"
#property version   "1.00"
#property script_show_inputs

input string InpBrokerSymbol = "XAUUSD";
input int InpBars = 50000;
input string InpFilename = "gold_xauusd_m15.csv";

void OnStart()
{
   // Explicitly reject other assets; some brokers append symbol suffixes.
   string normalized = InpBrokerSymbol;
   StringToUpper(normalized);
   if(StringFind(normalized, "XAUUSD") != 0)
   {
      Print("Rejected: this export is for XAUUSD symbols only");
      return;
   }
   if(InpBars <= 0 || InpBars > 250000)
   {
      Print("Rejected: InpBars must be in 1..250000");
      return;
   }
   if(!SymbolSelect(InpBrokerSymbol, true))
   {
      Print("Broker symbol unavailable: ", InpBrokerSymbol);
      return;
   }

   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   // Start index 1 excludes the currently forming candle.
   int count = CopyRates(InpBrokerSymbol, PERIOD_M15, 1, InpBars, rates);
   if(count <= 0)
   {
      Print("CopyRates failed: ", GetLastError());
      return;
   }
   int handle = FileOpen(InpFilename,
      FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("FileOpen failed: ", GetLastError());
      return;
   }

   FileWrite(handle, "broker_symbol", "timeframe", "server_time",
      "open", "high", "low", "close",
      "tick_volume", "spread_points", "real_volume");

   int digits = (int)SymbolInfoInteger(InpBrokerSymbol, SYMBOL_DIGITS);
   for(int i = 0; i < count; i++)
   {
      FileWrite(handle,
         InpBrokerSymbol,
         "M15",
         TimeToString(rates[i].time, TIME_DATE | TIME_SECONDS),
         DoubleToString(rates[i].open, digits),
         DoubleToString(rates[i].high, digits),
         DoubleToString(rates[i].low, digits),
         DoubleToString(rates[i].close, digits),
         (long)rates[i].tick_volume,
         (int)rates[i].spread,
         (long)rates[i].real_volume
      );
   }
   FileClose(handle);
   Print("Export complete: ", count, " closed M15 candles. Server timezone NOT verified.");
   Print("File is in terminal common data folder: ",
      TerminalInfoString(TERMINAL_COMMONDATA_PATH), "\\Files\\", InpFilename);
}
