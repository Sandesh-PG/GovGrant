'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Loader2 } from 'lucide-react';
import { cn } from './StatusBadge';

type Message = {
  role: 'user' | 'bot';
  content: string;
};

interface ChatWindowProps {
  onIntakeComplete: (profile: any) => void;
  onFieldsCollected?: (count: number) => void;
  sessionId: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function ChatWindow({ onIntakeComplete, onFieldsCollected, sessionId }: ChatWindowProps) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'bot', content: 'Hi! I\'m your GovGrant assistant. 👋\n\nI\'ll ask you 6 quick questions about your business to find the best government grants you\'re eligible for.\n\nReady? Just type anything to begin!' }
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  const handleSend = async () => {
    if (!input.trim() || isTyping) return;

    const userMessage = input.trim();
    const updatedMessages = [...messages, { role: 'user' as const, content: userMessage }];
    setMessages(updatedMessages);
    setInput('');
    setIsTyping(true);

    try {
      const token = localStorage.getItem('auth_token');
      const response = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          session_id: sessionId,
          message: userMessage,
          history: updatedMessages.map(m => ({
            role: m.role === 'user' ? 'user' : 'assistant',
            content: m.content,
          }))
        })
      });

      if (!response.ok) {
        const errorBody = await response.text();
        console.error(`[GovGrant] /api/chat failed — status: ${response.status}, body:`, errorBody);
        throw new Error(`Chat request failed (${response.status}): ${errorBody.slice(0, 200)}`);
      }

      const data = await response.json();
      console.log('[GovGrant] /api/chat response:', data);

      // Update fields collected count for progress bar
      if (onFieldsCollected && data.fields_collected !== undefined) {
        onFieldsCollected(data.fields_collected);
      }

      // Add bot reply
      setMessages(prev => [...prev, { role: 'bot', content: data.reply }]);

      // Check if intake is complete
      if (data.intake_complete) {
        setTimeout(() => {
          onIntakeComplete(data.profile);
        }, 2500);
      }

    } catch (err: any) {
      console.error('[GovGrant] Chat error:', err.message);
      setMessages(prev => [...prev, { role: 'bot', content: `Sorry, something went wrong. Please try again.\n\nDetails: ${err.message}` }]);
    } finally {
      setIsTyping(false);
    }
  };

  // Simple markdown-like bold rendering
  const renderContent = (content: string) => {
    const parts = content.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-bold">{part.slice(2, -2)}</strong>;
      }
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <div className="flex flex-col h-[600px] w-full max-w-2xl bg-white border rounded-2xl shadow-xl overflow-hidden">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50">
        {messages.map((m, i) => (
          <div key={i} className={cn("flex w-full", m.role === 'user' ? "justify-end" : "justify-start")}>
            <div className={cn("flex max-w-[80%] items-start space-x-2", m.role === 'user' ? "flex-row-reverse space-x-reverse" : "flex-row")}>
              <div className={cn("p-2 rounded-full flex-shrink-0", m.role === 'user' ? "bg-blue-600 text-white" : "bg-white border shadow-sm text-slate-600")}>
                {m.role === 'user' ? <User size={18} /> : <Bot size={18} />}
              </div>
              <div className={cn(
                "px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-line",
                m.role === 'user' ? "bg-blue-600 text-white rounded-tr-none" : "bg-white border shadow-sm text-slate-800 rounded-tl-none"
              )}>
                {renderContent(m.content)}
              </div>
            </div>
          </div>
        ))}
        {isTyping && (
          <div className="flex justify-start">
            <div className="flex max-w-[80%] items-start space-x-2">
              <div className="p-2 rounded-full bg-white border shadow-sm text-slate-600 flex-shrink-0">
                <Bot size={18} />
              </div>
              <div className="px-4 py-3 bg-white border shadow-sm text-slate-800 rounded-2xl rounded-tl-none flex items-center space-x-1">
                <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"></div>
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="p-4 border-t bg-white">
        <div className="relative flex items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Type your answer..."
            className="w-full px-4 py-3 pr-12 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isTyping}
            className="absolute right-2 p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}
