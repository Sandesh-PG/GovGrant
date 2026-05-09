'use client';

import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Shield, Loader2, Zap, CheckCircle2, Clock } from 'lucide-react';
import { AgentStatusCard } from '@/components/AgentStatusCard';
import { cn } from '@/components/StatusBadge';

type PipelineStatus = 'pending' | 'loading' | 'completed' | 'error';

const STAGES = [
  {
    key: 'intake',
    name: 'Intake Agent',
    description: 'Profile collected and verified',
    icon: '📋',
  },
  {
    key: 'research',
    name: 'Research Agent',
    description: 'Scanning 100+ state and central schemes',
    icon: '🔬',
  },
  {
    key: 'validation',
    name: 'Validator Agent',
    description: 'Checking eligibility and scoring matches',
    icon: '✅',
  },
  {
    key: 'report',
    name: 'Planner Agent',
    description: 'Generating documents and action plan',
    icon: '📄',
  },
];

type StageKey = 'intake' | 'research' | 'validation' | 'report';

const STATUS_MESSAGES: Record<string, string> = {
  intake_done:      'Profile verified — scanning government scheme databases…',
  research_done:    'Schemes found — validating your eligibility…',
  validation_done:  'Eligibility confirmed — building your personalised report…',
  report_ready:     'Report complete! Redirecting you to your results…',
  default:          'Preparing your profile for grant analysis…',
};

export default function ProcessingPage() {
  const [status, setStatus] = useState<Record<StageKey, PipelineStatus>>({
    intake: 'loading',
    research: 'pending',
    validation: 'pending',
    report: 'pending',
  });
  const [message, setMessage] = useState(STATUS_MESSAGES.default);
  const [schemeCount, setSchemeCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const didRun = useRef(false);

  useEffect(() => {
    if (didRun.current) return;
    didRun.current = true;

    const sessionId = localStorage.getItem('current_session_id');
    const token = localStorage.getItem('auth_token');

    if (!sessionId || !token) {
      router.push('/chat');
      return;
    }

    const runPipeline = async () => {
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/pipeline`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              session_id: sessionId,
              message: 'Analyze my profile and generate the grant report.',
              history: [],
            }),
          }
        );

        if (!response.ok) {
          const errText = await response.text();
          throw new Error(`Pipeline failed (${response.status}): ${errText.slice(0, 200)}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No readable stream');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split('\n\n');
          buffer = blocks.pop() || '';

          for (const block of blocks) {
            if (!block.includes('event: ')) continue;

            const eventType = block.split('event: ')[1]?.split('\n')[0]?.trim();
            const dataMatch = block.match(/data: (.*)/);
            const dataStr = dataMatch ? dataMatch[1] : '{}';

            let data: any = {};
            try { data = JSON.parse(dataStr); } catch { /* raw string */ }

            console.log('[Pipeline] event:', eventType, data);

            if (eventType === 'intake_done') {
              setStatus(prev => ({ ...prev, intake: 'completed', research: 'loading' }));
              setMessage(STATUS_MESSAGES.intake_done);
            } else if (eventType === 'research_done') {
              const count = Array.isArray(data) ? data.length : 0;
              setSchemeCount(count);
              setStatus(prev => ({ ...prev, research: 'completed', validation: 'loading' }));
              setMessage(`Found ${count} potential schemes — validating your eligibility…`);
            } else if (eventType === 'validation_done') {
              setStatus(prev => ({ ...prev, validation: 'completed', report: 'loading' }));
              setMessage(STATUS_MESSAGES.validation_done);
            } else if (eventType === 'report_ready') {
              setStatus(prev => ({
                ...prev,
                intake: 'completed',
                research: 'completed',
                validation: 'completed',
                report: 'completed',
              }));
              setMessage(STATUS_MESSAGES.report_ready);
              setTimeout(() => {
                router.push(`/results/${sessionId}`);
              }, 1200);
            }
          }
        }
      } catch (err: any) {
        console.error('[Pipeline] error:', err.message);
        setError(err.message);
        // Still redirect to results after a delay — report may have been partially generated
        setTimeout(() => {
          const sid = localStorage.getItem('current_session_id');
          if (sid) router.push(`/results/${sid}`);
        }, 4000);
      }
    };

    runPipeline();
  }, [router]);

  const allDone = Object.values(status).every(s => s === 'completed');

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-xl space-y-10">

        {/* Header */}
        <div className="text-center space-y-4">
          <div className={cn(
            'inline-flex p-4 rounded-3xl shadow-xl border border-white/10 mb-2',
            allDone ? 'bg-green-500/20 border-green-400/30' : 'bg-white/10',
          )}>
            {allDone
              ? <CheckCircle2 className="w-8 h-8 text-green-400" />
              : <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
            }
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight">
            {allDone ? 'Report Ready!' : 'Building your grant report'}
          </h1>
          <p className={cn(
            'font-medium text-sm transition-all',
            error ? 'text-red-300' : 'text-blue-200',
          )}>
            {error
              ? `⚠ Pipeline error — redirecting to partial results…`
              : message}
          </p>
        </div>

        {/* Stage cards */}
        <div className="grid grid-cols-1 gap-3">
          {STAGES.map((stage) => (
            <div
              key={stage.key}
              className={cn(
                'flex items-center gap-4 px-5 py-4 rounded-2xl border transition-all duration-500',
                status[stage.key as StageKey] === 'completed'
                  ? 'bg-green-500/10 border-green-500/30 text-green-100'
                  : status[stage.key as StageKey] === 'loading'
                  ? 'bg-blue-500/10 border-blue-400/40 text-blue-100 shadow-lg shadow-blue-500/10'
                  : status[stage.key as StageKey] === 'error'
                  ? 'bg-red-500/10 border-red-500/30 text-red-200'
                  : 'bg-white/5 border-white/10 text-slate-400',
              )}
            >
              <div className="text-2xl flex-shrink-0">{stage.icon}</div>
              <div className="flex-1 min-w-0">
                <p className="font-bold text-sm">{stage.name}</p>
                <p className="text-xs opacity-70 truncate">{stage.description}</p>
              </div>
              <div className="flex-shrink-0">
                {status[stage.key as StageKey] === 'completed' && (
                  <CheckCircle2 size={18} className="text-green-400" />
                )}
                {status[stage.key as StageKey] === 'loading' && (
                  <Loader2 size={18} className="text-blue-400 animate-spin" />
                )}
                {status[stage.key as StageKey] === 'pending' && (
                  <Clock size={18} className="text-slate-500" />
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Fun fact card */}
        <div className="bg-blue-500/10 rounded-2xl p-5 border border-blue-400/20 flex items-start gap-4">
          <Zap size={20} className="text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="text-blue-200 font-bold mb-1">Did you know?</p>
            <p className="text-blue-300 leading-relaxed">
              Gemini 2.0 Flash is searching scheme databases from{' '}
              {schemeCount !== null
                ? `${schemeCount} matching programmes`
                : 'central and state government portals'}
              {' '}to find the best grants for your business.
            </p>
          </div>
        </div>

      </div>
    </div>
  );
}
