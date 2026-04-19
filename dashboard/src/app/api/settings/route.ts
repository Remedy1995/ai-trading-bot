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

    if (body.timeframe) settings.timeframe = body.timeframe;
    if (body.trade_amount) settings.trade_amount = Number(body.trade_amount);

    fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2));

    return NextResponse.json({ success: true, settings });
  } catch (error) {
    console.error('Settings API Error:', error);
    return NextResponse.json({ error: 'Failed to update settings' }, { status: 500 });
  }
}
