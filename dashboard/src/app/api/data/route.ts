import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET() {
  try {
    const parentDir = path.resolve(process.cwd(), '..');
    
    let botResults = [];
    let backtestResults = [];
    let sentimentResults = [];
    
    const botResultsPath = path.join(parentDir, 'bot_results.json');
    if (fs.existsSync(botResultsPath)) {
      botResults = JSON.parse(fs.readFileSync(botResultsPath, 'utf8'));
    }
    
    const backtestResultsPath = path.join(parentDir, 'backtest_results.json');
    if (fs.existsSync(backtestResultsPath)) {
      backtestResults = JSON.parse(fs.readFileSync(backtestResultsPath, 'utf8'));
    }

    const sentimentResultsPath = path.join(parentDir, 'sentiment_results.json');
    if (fs.existsSync(sentimentResultsPath)) {
      sentimentResults = JSON.parse(fs.readFileSync(sentimentResultsPath, 'utf8'));
    }

    return NextResponse.json({
      botResults,
      backtestResults,
      sentimentResults,
      lastUpdated: new Date().toISOString()
    });
  } catch (error) {
    console.error('API Error:', error);
    return NextResponse.json({ error: 'Failed to read data files' }, { status: 500 });
  }
}
