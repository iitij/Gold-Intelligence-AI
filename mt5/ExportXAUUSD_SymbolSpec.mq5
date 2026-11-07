//+------------------------------------------------------------------+
//| Gold Intelligence AI - read-only XAUUSD symbol specification     |
//| Never reads account identity, margin balance, positions or orders|
//| Never sends trade requests. Snapshot only; not historical DST.   |
//+------------------------------------------------------------------+
#property copyright "Gold Intelligence AI contributors"
#property version   "1.00"
#property script_show_inputs

input string InpBrokerSymbol = "XAUUSD";
input string InpFilename = "gold_xauusd_symbol_spec.csv";

void OnStart()
{
   string normalized = InpBrokerSymbol;
   StringToUpper(normalized);
   if(StringFind(normalized, "XAUUSD") != 0)
   {
      Print("Rejected: explicit XAUUSD broker symbol only");
      return;
   }
   if(!SymbolSelect(InpBrokerSymbol, true))
   {
      Print("Symbol unavailable: ", InpBrokerSymbol);
      return;
   }

   int file = FileOpen(InpFilename,
                         FILE_COMMON | FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(file == INVALID_HANDLE)
   {
      Print("FileOpen failed: ", GetLastError());
      return;
   }

   FileWrite(file, "field", "value");
   FileWrite(file, "schema_version", "1");
   FileWrite(file, "asset_id", "XAUUSD");
   FileWrite(file, "broker_symbol", InpBrokerSymbol);
   FileWrite(file, "snapshot_server_time",
      TimeToString(TimeTradeServer(), TIME_DATE | TIME_SECONDS));
   FileWrite(file, "snapshot_local_estimated_utc",
      TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS));
   FileWrite(file, "observed_server_offset_seconds",
      StringFormat("%I64d", (long)(TimeTradeServer() - TimeGMT())));
   FileWrite(file, "point", DoubleToString(
      SymbolInfoDouble(InpBrokerSymbol, SYMBOL_POINT), 12));
   FileWrite(file, "digits", (int)SymbolInfoInteger(
      InpBrokerSymbol, SYMBOL_DIGITS));
   FileWrite(file, "tick_size", DoubleToString(
      SymbolInfoDouble(InpBrokerSymbol, SYMBOL_TRADE_TICK_SIZE), 12));
   FileWrite(file, "tick_value_profit", DoubleToString(
      SymbolInfoDouble(InpBrokerSymbol, SYMBOL_TRADE_TICK_VALUE_PROFIT), 12));
   FileWrite(file, "tick_value_loss", DoubleToString(
      SymbolInfoDouble(InpBrokerSymbol, SYMBOL_TRADE_TICK_VALUE_LOSS), 12));
   FileWrite(file, "contract_size", DoubleToString(
      SymbolInfoDouble(InpBrokerSymbol, SYMBOL_TRADE_CONTRACT_SIZE), 12));
   FileWrite(file, "volume_min", DoubleToString(
      SymbolInfoDouble(InpBrokerSymbol, SYMBOL_VOLUME_MIN), 12));
   FileWrite(file, "volume_max", DoubleToString(
      SymbolInfoDouble(InpBrokerSymbol, SYMBOL_VOLUME_MAX), 12));
   FileWrite(file, "volume_step", DoubleToString(
      SymbolInfoDouble(InpBrokerSymbol, SYMBOL_VOLUME_STEP), 12));
   FileWrite(file, "stops_level_points", (int)SymbolInfoInteger(
      InpBrokerSymbol, SYMBOL_TRADE_STOPS_LEVEL));
   FileWrite(file, "freeze_level_points", (int)SymbolInfoInteger(
      InpBrokerSymbol, SYMBOL_TRADE_FREEZE_LEVEL));
   FileWrite(file, "currency_profit", SymbolInfoString(
      InpBrokerSymbol, SYMBOL_CURRENCY_PROFIT));
   FileWrite(file, "trade_calc_mode", (int)SymbolInfoInteger(
      InpBrokerSymbol, SYMBOL_TRADE_CALC_MODE));
   FileWrite(file, "trade_mode", (int)SymbolInfoInteger(
      InpBrokerSymbol, SYMBOL_TRADE_MODE));
   FileWrite(file, "trade_execution_mode", (int)SymbolInfoInteger(
      InpBrokerSymbol, SYMBOL_TRADE_EXEMODE));
   FileWrite(file, "historical_dst_verified", "false");
   FileWrite(file, "contains_account_identifiers", "false");
   FileClose(file);

   Print("Read-only XAUUSD symbol spec saved (historical timezone not verified)");
   Print("COMMON DATA FILES: ",
         TerminalInfoString(TERMINAL_COMMONDATA_PATH),
         "\\Files\\", InpFilename);
}
