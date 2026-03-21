import { NextResponse } from 'next/server';

const GATEWAY_URL = process.env.GATEWAY_URL ?? 'http://gateway:8000';

export async function GET(request) {
  const auth = request.headers.get('authorization') ?? '';

  const res = await fetch(`${GATEWAY_URL}/me`, {
    headers: { Authorization: auth },
  });

  if (!res.ok) {
    return NextResponse.json({ message: 'Unauthorized' }, { status: res.status });
  }

  const data = await res.json();
  return NextResponse.json({
    user: { id: data.user_id, email: data.email, registered: data.registered },
  });
}
