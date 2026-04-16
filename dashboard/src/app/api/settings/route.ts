import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const parentDir = process.env.DATA_DIR || path.resolve(process.cwd(), '..');
    const settingsPath = path.join(parentDir, 'settings.json');

    let settings = { timeframe: '5m' };
    if (fs.existsSync(settingsPath)) {
      settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    }

    if (body.timeframe) {
      settings.timeframe = body.timeframe;
    }

    fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2));

    return NextResponse.json({ success: true, settings });
  } catch (error) {
    console.error('Settings API Error:', error);
    return NextResponse.json({ error: 'Failed to update settings' }, { status: 500 });
  }
}
