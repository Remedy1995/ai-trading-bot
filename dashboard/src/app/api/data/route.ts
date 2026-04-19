import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

function readJson(filePath: string, fallback: unknown = []) {
  try {
    if (fs.existsSync(filePath)) {
      return JSON.parse(fs.readFileSync(filePath, 'utf8'));
    }
  } catch { /* ignore parse errors */ }
  return fallback;
}

function readTextLines(filePath: string) {
  try {
    if (fs.existsSync(filePath)) {
      const content = fs.readFileSync(filePath, 'utf8');
      return content.split('\n').filter(line => line.trim().length > 0).reverse(); // Reverse for newest first
    }
  } catch { /* ignore parse errors */ }
  return [];
}

export async function GET() {
  try {
    const parentDir = process.env.DATA_DIR || path.resolve(process.cwd(), '..');

    // Single source of truth for all real-time data
    const botState            = readJson(path.join(parentDir, 'bot_state.json'), {});

    // Static / historical files (not real-time)
    const botResults          = readJson(path.join(parentDir, 'bot_results.json'));
    const backtestResults     = readJson(path.join(parentDir, 'backtest_results.json'));
    const sentimentResults    = readJson(path.join(parentDir, 'sentiment_results.json'));
    const enhancedBacktest    = readJson(path.join(parentDir, 'enhanced_backtest_results.json'));
    const tradeHistory        = readTextLines(path.join(parentDir, 'trade_history.txt'));
    const settings            = readJson(path.join(parentDir, 'settings.json'), { timeframe: '1h', trade_amount: 15 });

    // Extract from single source of truth
    const enhancedResults     = { results: botState.signals ?? [], generated: botState.generated, aggregate_stats: botState.stats ?? {} };
    const tradeState          = botState.open_trades ?? {};
    const balance             = botState.balance ?? { usdt_free: null, usdt_total: null };

    return NextResponse.json({
      botResults,
      backtestResults,
      sentimentResults,
      enhancedResults,
      enhancedBacktest,
      tradeHistory,
      settings,
      tradeState,
      balance,
      lastUpdated: new Date().toISOString(),
    });
  } catch (error) {
    console.error('API Error:', error);
    return NextResponse.json({ error: 'Failed to read data files' }, { status: 500 });
  }
}
