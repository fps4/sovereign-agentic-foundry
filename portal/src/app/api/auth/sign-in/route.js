import { NextResponse } from 'next/server';

const GATEWAY_URL = process.env.GATEWAY_URL ?? 'http://gateway:8000';

export async function POST(request) {
  const { email, password } = await request.json();

  const res = await fetch(`${GATEWAY_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    return NextResponse.json(detail, { status: res.status });
  }

  const { token, user_id } = await res.json();
  return NextResponse.json({ accessToken: token, user: { id: user_id, email } });
}
