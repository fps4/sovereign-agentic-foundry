'use client';

import { useRef, useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Avatar from '@mui/material/Avatar';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import CircularProgress from '@mui/material/CircularProgress';

import { DashboardContent } from 'src/layouts/dashboard';

import { Iconify } from 'src/components/iconify';

import { useAuthContext } from 'src/auth/hooks';
import { JWT_STORAGE_KEY } from 'src/auth/context/jwt/constant';

// ----------------------------------------------------------------------

const INTRO_MESSAGE = {
  role: 'assistant',
  content:
    "Hi! I'm your app builder. Describe the web app you'd like to create and I'll ask a few quick questions to nail down the spec — then we'll build it automatically.",
};

// ----------------------------------------------------------------------

function MessageBubble({ message }) {
  const isUser = message.role === 'user';

  return (
    <Stack
      direction="row"
      spacing={1.5}
      sx={{ justifyContent: isUser ? 'flex-end' : 'flex-start', mb: 2 }}
    >
      {!isUser && (
        <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main', fontSize: 13 }}>AI</Avatar>
      )}

      <Box
        sx={{
          maxWidth: '70%',
          px: 2,
          py: 1.5,
          borderRadius: 2,
          bgcolor: isUser ? 'primary.main' : 'background.neutral',
          color: isUser ? 'primary.contrastText' : 'text.primary',
          borderTopRightRadius: isUser ? 0 : 2,
          borderTopLeftRadius: isUser ? 2 : 0,
        }}
      >
        <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
          {message.content}
        </Typography>
      </Box>

      {isUser && (
        <Avatar sx={{ width: 32, height: 32, bgcolor: 'secondary.main', fontSize: 13 }}>Me</Avatar>
      )}
    </Stack>
  );
}

// ----------------------------------------------------------------------

function SpecLockedBanner({ spec }) {
  return (
    <Card
      sx={{
        p: 3,
        mb: 3,
        border: '1px solid',
        borderColor: 'success.light',
        bgcolor: 'success.lighter',
      }}
    >
      <Stack direction="row" spacing={1.5} alignItems="center" mb={1.5}>
        <Iconify
          icon="eva:checkmark-circle-2-fill"
          sx={{ color: 'success.main', width: 24, height: 24 }}
        />
        <Typography variant="subtitle1" color="success.dark">
          Spec locked — building your app
        </Typography>
      </Stack>

      <Typography variant="body2" color="text.secondary" mb={0.5}>
        <strong>{spec.title}</strong> &nbsp;·&nbsp; {spec.app_type}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {spec.description}
      </Typography>
    </Card>
  );
}

// ----------------------------------------------------------------------

export function ChatView() {
  const { user } = useAuthContext();
  const [messages, setMessages] = useState([INTRO_MESSAGE]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [lockedSpec, setLockedSpec] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || loading || lockedSpec) return;

    const userMsg = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const token =
        typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(JWT_STORAGE_KEY) : null;

      const history = messages.map((m) => ({ role: m.role, content: m.content }));

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: text, history }),
      });

      if (!res.ok) throw new Error('Chat request failed');

      const data = await res.json();
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }]);

      if (data.spec_locked && data.spec) {
        setLockedSpec(data.spec);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Sorry, something went wrong. Please try again.' },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, lockedSpec, messages]);

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    },
    [send]
  );

  return (
    <DashboardContent maxWidth="md">
      <Typography variant="h4" sx={{ mb: { xs: 3, md: 4 } }}>
        Build an App
      </Typography>

      {lockedSpec && <SpecLockedBanner spec={lockedSpec} />}

      <Card sx={{ display: 'flex', flexDirection: 'column', height: 560 }}>
        {/* Message thread */}
        <Box sx={{ flex: 1, overflowY: 'auto', p: 3 }}>
          {messages.map((m, i) => (
            // eslint-disable-next-line react/no-array-index-key
            <MessageBubble key={i} message={m} />
          ))}

          {loading && (
            <Stack direction="row" spacing={1.5} alignItems="center" mb={2}>
              <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main', fontSize: 13 }}>
                AI
              </Avatar>
              <CircularProgress size={18} />
            </Stack>
          )}

          <div ref={bottomRef} />
        </Box>

        {/* Input bar */}
        <Box sx={{ p: 2, borderTop: '1px solid', borderColor: 'divider' }}>
          <Stack direction="row" spacing={1} alignItems="flex-end">
            <TextField
              fullWidth
              multiline
              maxRows={4}
              size="small"
              placeholder={
                lockedSpec ? 'Spec locked — app is being built…' : 'Describe your app…'
              }
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading || !!lockedSpec}
            />
            <IconButton
              color="primary"
              onClick={send}
              disabled={!input.trim() || loading || !!lockedSpec}
            >
              <Iconify icon="eva:paper-plane-fill" />
            </IconButton>
          </Stack>
        </Box>
      </Card>
    </DashboardContent>
  );
}
