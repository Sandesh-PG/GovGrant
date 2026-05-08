'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChatWindow } from '@/components/ChatWindow';
import { Shield, ChevronRight, Check } from 'lucide-react';
import { cn } from '@/components/StatusBadge';
import { api } from '@/lib/api';

const PROGRESS_FIELDS = [
  'Business name',
  'Entity type',
  'Sector',
  'State',
  'Team size',
  'Revenue'
];

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [fieldsCollected, setFieldsCollected] = useState(0);
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      router.push('/login');
      return;
    }

    const initSession = async () => {
      try {
        // Always create a fresh session when arriving at /chat
        // A stale session_id in localStorage could belong to a different user → 403
        const { session_id } = await api.createSession();
        localStorage.setItem('current_session_id', session_id);
        setSessionId(session_id);
      } catch (err) {
        console.error('Failed to create session', err);
        // If session creation fails, redirect to login (token is likely expired)
        localStorage.removeItem('auth_token');
        router.push('/login');
      }
    };

    initSession();
  }, [router]);

  const handleIntakeComplete = (profile: any) => {
    setFieldsCollected(6);
    localStorage.setItem('current_session_id', sessionId!);
    setTimeout(() => {
      router.push('/processing');
    }, 1500);
  };

  const handleFieldsCollected = (count: number) => {
    setFieldsCollected(count);
  };

  if (!sessionId) return null;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="px-6 py-4 bg-white border-b border-slate-100 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center space-x-2">
          <Shield className="text-blue-600 w-5 h-5" />
          <span className="font-outfit font-bold text-lg text-slate-900">GovGrant</span>
        </div>
        
        <div className="flex items-center space-x-4">
          <div className="hidden md:flex items-center space-x-1">
            {PROGRESS_FIELDS.map((field, i) => (
              <div key={i} className="flex items-center">
                <div className={cn(
                  "flex items-center text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded-lg",
                  fieldsCollected > i ? "text-green-600 bg-green-50" : "text-slate-400"
                )}>
                  {field}
                  {fieldsCollected > i && <Check size={10} className="ml-1" />}
                </div>
                {i < PROGRESS_FIELDS.length - 1 && <ChevronRight size={12} className="text-slate-300" />}
              </div>
            ))}
          </div>
          <div className="w-32 md:w-48 h-2 bg-slate-100 rounded-full overflow-hidden">
            <div 
              className="h-full bg-blue-600 transition-all duration-500 ease-out" 
              style={{ width: `${(fieldsCollected / 6) * 100}%` }}
            />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex flex-col items-center justify-center p-6 space-y-8">
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-outfit font-extrabold text-slate-900 tracking-tight">
            Tell us about your business
          </h1>
          <p className="text-slate-500 max-w-lg mx-auto">
            Our AI needs a few details to accurately match you with the right government schemes.
          </p>
        </div>

        <ChatWindow 
          sessionId={sessionId} 
          onIntakeComplete={handleIntakeComplete}
          onFieldsCollected={handleFieldsCollected}
        />
        
        <p className="text-xs text-slate-400 font-medium flex items-center">
          <Shield size={12} className="mr-1.5 text-blue-500" />
          Your data is secure and used only for grant matching.
        </p>
      </main>
    </div>
  );
}
