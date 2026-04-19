import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const parentDir = process.env.DATA_DIR || path.resolve(process.cwd(), '..');
    const settingsPath = path.join(parentDir, 'settings.json');

    let settings: any = { timeframe: '1h', trade_amount: 15 };
    if (fs.existsSync(settingsPath)) {
      settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    }

    const validTimeframes = ['5m', '15m', '1h', '4h', '1d'];
    if (body.timeframe && validTimeframes.includes(body.timeframe)) settings.timeframe = body.timeframe;
    if (body.trade_amount) {
      const amt = Number(body.trade_amount);
      if (amt >= 5 && amt <= 10000) settings.trade_amount = amt;  // min $5 to meet exchange minimums
    }

    fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2));

    return NextResponse.json({ success: true, settings });
  } catch (error) {
    console.error('Settings API Error:', error);
    return NextResponse.json({ error: 'Failed to update settings' }, { status: 500 });
  }
}
