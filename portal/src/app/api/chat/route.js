import { NextResponse } from 'next/server';

const GATEWAY_URL = process.env.GATEWAY_URL ?? 'http://gateway:8000';

export async function POST(request) {
  const auth = request.headers.get('authorization') ?? '';
  const body = await request.json();

  const res = await fetch(`${GATEWAY_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: auth,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    return NextResponse.json(detail, { status: res.status });
  }

  const data = await res.json();
  return NextResponse.json(data);
}
