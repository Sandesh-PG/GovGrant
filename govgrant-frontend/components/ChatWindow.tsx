'use client';

import { useState, useRef, useEffect } from 'react';
import {
  Send, Bot, Loader2, Check, User,
  ChevronRight, ExternalLink, Building2, MapPin,
  Briefcase, TrendingUp, Users, Target, FileText, Award,
} from 'lucide-react';
import { cn } from './StatusBadge';

// ─── Types ─────────────────────────────────────────────────────────────────────

type AgentResponse = {
  step: number | 'summary' | 'schemes';
  message: string;
  input_type: 'options' | 'text' | 'confirm' | 'none';
  options: string[];
  field: string;
  collected: Record<string, string>;
};

type Message = {
  role: 'user' | 'bot';
  text: string;                   // display text
  agentResponse?: AgentResponse;  // structured payload (bot only)
};

interface ChatWindowProps {
  onIntakeComplete: (profile: any) => void;
  onFieldsCollected?: (count: number) => void;
  sessionId: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─── Step icon map ─────────────────────────────────────────────────────────────

const STEP_ICONS: Record<string, React.ReactNode> = {
  name_and_org: <User size={14} />,
  state: <MapPin size={14} />,
  sector: <Briefcase size={14} />,
  business_stage: <TrendingUp size={14} />,
  annual_turnover: <TrendingUp size={14} />,
  employee_count: <Users size={14} />,
  funding_type: <Target size={14} />,
  funding_purpose: <Target size={14} />,
  legal_registration: <FileText size={14} />,
  certifications: <Award size={14} />,
};

const FIELD_LABELS: Record<string, string> = {
  name_and_org: 'Name & Organisation',
  state: 'State',
  sector: 'Sector',
  business_stage: 'Business Stage',
  annual_turnover: 'Annual Turnover',
  employee_count: 'Employees',
  funding_type: 'Funding Type',
  funding_purpose: 'Funding Purpose',
  legal_registration: 'Registration',
  certifications: 'Certifications',
};

// ─── Scheme card parser ────────────────────────────────────────────────────────

function parseSchemes(message: string) {
  // Split on numbered list items or "**Scheme Name**" headings
  const blocks = message
    .split(/\n(?=\d+\.\s|\*\*[^*]+\*\*)/)
    .map(b => b.trim())
    .filter(Boolean);

  return blocks.map((block) => {
    // Extract scheme name from first bold or numbered line
    const nameMatch = block.match(/^(?:\d+\.\s+)?\*\*([^*]+)\*\*/) || block.match(/^(?:\d+\.\s+)?([^\n]+)/);
    const name = nameMatch?.[1]?.trim() ?? 'Scheme';
    const rest = block.replace(nameMatch?.[0] ?? '', '').trim();

    // Extract lines
    const lines = rest.split('\n').map(l => l.trim()).filter(Boolean);
    return { name, lines };
  });
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function BotAvatar() {
  return (
    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center flex-shrink-0 shadow-md">
      <Bot size={16} className="text-white" />
    </div>
  );
}

function UserAvatar() {
  return (
    <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center flex-shrink-0 shadow-md">
      <User size={16} className="text-white" />
    </div>
  );
}

function MarkdownText({ text }: { text: string }) {
  // Bold + line-break renderer
  const lines = text.split('\n');
  return (
    <div className="space-y-1 leading-relaxed text-sm">
      {lines.map((line, i) => {
        const parts = line.split(/(\*\*[^*]+\*\*)/g);
        return (
          <p key={i} className={line === '' ? 'h-2' : ''}>
            {parts.map((part, j) =>
              part.startsWith('**') && part.endsWith('**')
                ? <strong key={j} className="font-semibold">{part.slice(2, -2)}</strong>
                : <span key={j}>{part}</span>
            )}
          </p>
        );
      })}
    </div>
  );
}

function OptionPills({
  options,
  onSelect,
  disabled,
}: {
  options: string[];
  onSelect: (v: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {options.map((opt) => (
        <button
          key={opt}
          disabled={disabled}
          onClick={() => onSelect(opt)}
          id={`option-${opt.replace(/\s+/g, '-').toLowerCase()}`}
          className={cn(
            'px-3 py-1.5 rounded-full border text-sm font-medium transition-all duration-150',
            'hover:bg-blue-600 hover:text-white hover:border-blue-600 hover:shadow-sm',
            'focus:outline-none focus:ring-2 focus:ring-blue-400',
            disabled
              ? 'opacity-40 cursor-not-allowed'
              : 'bg-white text-slate-700 border-slate-300 cursor-pointer active:scale-95',
          )}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

function ConfirmButtons({
  options,
  onSelect,
  onDirectComplete,
  disabled,
}: {
  options: string[];
  onSelect: (v: string) => void;
  onDirectComplete?: () => void;
  disabled: boolean;
}) {
  const [positive, negative] = options.length >= 2 ? options : ['Yes', 'No'];
  return (
    <div className="flex gap-3 mt-3">
      <button
        disabled={disabled}
        onClick={() => onDirectComplete ? onDirectComplete() : onSelect(positive)}
        id="confirm-yes"
        className={cn(
          'flex-1 py-2.5 rounded-xl text-sm font-semibold transition-all duration-150',
          'bg-blue-600 text-white hover:bg-blue-700 active:scale-95 shadow-sm',
          disabled && 'opacity-40 cursor-not-allowed',
        )}
      >
        {positive}
      </button>
      <button
        disabled={disabled}
        onClick={() => onSelect(negative)}
        id="confirm-no"
        className={cn(
          'flex-1 py-2.5 rounded-xl text-sm font-semibold transition-all duration-150',
          'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 active:scale-95',
          disabled && 'opacity-40 cursor-not-allowed',
        )}
      >
        {negative}
      </button>
    </div>
  );
}

function ProfileSummaryCard({ collected }: { collected: Record<string, string> }) {
  const rows: { icon: React.ReactNode; label: string; value: string }[] = [];
  Object.entries(FIELD_LABELS).forEach(([key, label]) => {
    if (collected[key]) {
      rows.push({ icon: STEP_ICONS[key], label, value: collected[key] });
    }
  });

  return (
    <div className="mt-3 rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-blue-50 overflow-hidden shadow-sm">
      <div className="px-4 py-3 bg-blue-600/10 border-b border-blue-100 flex items-center gap-2">
        <Building2 size={14} className="text-blue-600" />
        <span className="text-xs font-bold uppercase tracking-widest text-blue-700">Your Profile</span>
      </div>
      <div className="divide-y divide-slate-100">
        {rows.map(({ icon, label, value }) => (
          <div key={label} className="flex items-center gap-3 px-4 py-2.5">
            <span className="text-blue-500 flex-shrink-0">{icon}</span>
            <span className="text-xs text-slate-500 w-28 flex-shrink-0">{label}</span>
            <span className="text-xs font-semibold text-slate-800 truncate">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SchemesDisplay({ message }: { message: string }) {
  const schemes = parseSchemes(message);

  if (schemes.length === 0) {
    return <MarkdownText text={message} />;
  }

  return (
    <div className="space-y-3 mt-3">
      {schemes.map((scheme, i) => (
        <div
          key={i}
          className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden"
        >
          <div className="px-4 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 flex items-center gap-2">
            <div className="w-6 h-6 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
              <span className="text-xs font-bold text-white">{i + 1}</span>
            </div>
            <span className="text-sm font-bold text-white">{scheme.name}</span>
          </div>
          <div className="px-4 py-3 space-y-1">
            {scheme.lines.map((line, j) => {
              const parts = line.split(/(\*\*[^*]+\*\*)/g);
              return (
                <p key={j} className="text-xs text-slate-600 leading-relaxed">
                  {parts.map((part, k) =>
                    part.startsWith('**') && part.endsWith('**')
                      ? <strong key={k} className="font-semibold text-slate-800">{part.slice(2, -2)}</strong>
                      : <span key={k}>{part}</span>
                  )}
                </p>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Progress dots ─────────────────────────────────────────────────────────────

function StepProgress({ current }: { current: number | string }) {
  const total = 10;
  const stepNum = typeof current === 'number' ? current : total;
  return (
    <div className="flex items-center gap-1 px-4 py-2 bg-white border-b border-slate-100">
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          className={cn(
            'h-1 flex-1 rounded-full transition-all duration-300',
            i < stepNum ? 'bg-blue-600' : 'bg-slate-200',
          )}
        />
      ))}
      <span className="text-[10px] font-bold text-slate-400 ml-1 whitespace-nowrap">
        {stepNum}/{total}
      </span>
    </div>
  );
}

// ─── Main component ─────────────────────────────────────────────────────────────

const OPENING_AGENT_RESPONSE: AgentResponse = {
  step: 1,
  message:
    "Hello! Welcome. I'm your Government Funding Intake Assistant. I'm here to help you identify and apply for central and state government funding schemes that best fit your business.\n\nThis will just take a few minutes. Could you please share your full name and the name of your business or organisation?",
  input_type: 'text',
  options: [],
  field: 'name_and_org',
  collected: {},
};

export function ChatWindow({ onIntakeComplete, onFieldsCollected, sessionId }: ChatWindowProps) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'bot', text: OPENING_AGENT_RESPONSE.message, agentResponse: OPENING_AGENT_RESPONSE },
  ]);
  const [textInput, setTextInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState<number | string>(1);
  const [isSummaryComplete, setIsSummaryComplete] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // The most recent bot message drives the input UI
  const latestBot = [...messages].reverse().find(m => m.role === 'bot');
  const latestAR = latestBot?.agentResponse;
  const inputType = latestAR?.input_type ?? 'text';
  const inputOptions = latestAR?.options ?? [];
  const isDone = isSummaryComplete || latestAR?.step === 'schemes';

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  // ── Direct pipeline trigger — bypasses Gemini for the confirm step ──────────
  const triggerPipeline = () => {
    setIsSummaryComplete(true);
    setCurrentStep(10);
    if (onFieldsCollected) onFieldsCollected(10);
    // Show a user message
    setMessages(prev => [...prev, { role: 'user', text: 'Yes, show me eligible schemes' }]);
    // Redirect to processing page after a brief animation
    setTimeout(() => {
      onIntakeComplete({});
    }, 1200);
  };

  // ── Send a message (either typed text or a button selection) ──────────────
  const sendMessage = async (userText: string) => {
    if (!userText.trim() || isLoading) return;

    const userMsg: Message = { role: 'user', text: userText };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setTextInput('');
    setIsLoading(true);

    try {
      const token = localStorage.getItem('auth_token');
      const history = updatedMessages.map(m => ({
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.text,
      }));

      const res = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          session_id: sessionId,
          message: userText,
          history,
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`Chat failed (${res.status}): ${errText.slice(0, 200)}`);
      }

      const data = await res.json();
      const ar: AgentResponse | undefined = data.agent_response;
      const replyText: string = ar?.message ?? data.reply ?? '';

      // Update progress bar
      const step = ar?.step ?? data.fields_collected;
      setCurrentStep(step);
      if (onFieldsCollected) {
        onFieldsCollected(typeof step === 'number' ? step : 10);
      }

      // Add bot reply
      const botMsg: Message = { role: 'bot', text: replyText, agentResponse: ar };
      setMessages(prev => [...prev, botMsg]);

      // Trigger pipeline when schemes are shown
      if (data.intake_complete && ar?.step === 'schemes') {
        setTimeout(() => onIntakeComplete(data.profile), 2000);
      }
    } catch (err: any) {
      setMessages(prev => [
        ...prev,
        {
          role: 'bot',
          text: `Sorry, something went wrong. Please try again.\n\nDetails: ${err.message}`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  // ─── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col w-full max-w-2xl bg-white border border-slate-200 rounded-2xl shadow-xl overflow-hidden">

      {/* Step progress bar */}
      <StepProgress current={currentStep} />

      {/* Message list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-5 space-y-5 bg-slate-50 min-h-[420px] max-h-[560px]">
        {messages.map((msg, idx) => {
          const ar = msg.agentResponse;
          const isLast = idx === messages.length - 1;

          return (
            <div
              key={idx}
              className={cn(
                'flex items-start gap-3',
                msg.role === 'user' ? 'flex-row-reverse' : 'flex-row',
              )}
            >
              {msg.role === 'bot' ? <BotAvatar /> : <UserAvatar />}

              <div className={cn('max-w-[85%]', msg.role === 'user' ? 'items-end' : 'items-start', 'flex flex-col')}>
                {/* Bubble */}
                <div
                  className={cn(
                    'px-4 py-3 rounded-2xl',
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white rounded-tr-none text-sm'
                      : 'bg-white border border-slate-200 shadow-sm text-slate-800 rounded-tl-none',
                  )}
                >
                  {msg.role === 'user' ? (
                    <p className="text-sm leading-relaxed">{msg.text}</p>
                  ) : ar?.step === 'schemes' ? (
                    <>
                      <MarkdownText text={ar.message.split('\n')[0]} />
                      <SchemesDisplay message={ar.message} />
                    </>
                  ) : ar?.step === 'summary' ? (
                    <>
                      <MarkdownText text={ar.message} />
                      {ar.collected && Object.keys(ar.collected).length > 0 && (
                        <ProfileSummaryCard collected={ar.collected} />
                      )}
                    </>
                  ) : (
                    <MarkdownText text={msg.text} />
                  )}
                </div>

                {/* Interactive controls — only shown on the LAST bot message while not loading */}
                {msg.role === 'bot' && isLast && !isLoading && ar && (
                  <>
                    {ar.input_type === 'options' && ar.options.length > 0 && (
                      <OptionPills
                        options={ar.options}
                        onSelect={sendMessage}
                        disabled={isDone}
                      />
                    )}
                    {ar.input_type === 'confirm' && (
                      <ConfirmButtons
                        options={ar.options.length >= 2 ? ar.options : ['Yes, show me eligible schemes', 'I want to edit my answers']}
                        onSelect={sendMessage}
                        onDirectComplete={ar.step === 'summary' ? triggerPipeline : undefined}
                        disabled={isDone}
                      />
                    )}
                  </>
                )}
              </div>
            </div>
          );
        })}

        {/* Typing indicator */}
        {isLoading && (
          <div className="flex items-start gap-3">
            <BotAvatar />
            <div className="px-4 py-3 bg-white border border-slate-200 shadow-sm rounded-2xl rounded-tl-none flex items-center gap-1.5">
              <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
              <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
              <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" />
            </div>
          </div>
        )}
      </div>

      {/* Text input — shown when input_type is "text" or there is no agent response */}
      {(inputType === 'text' || !latestAR) && !isDone && (
        <div className="p-4 border-t border-slate-100 bg-white">
          <div className="relative flex items-center">
            <input
              id="chat-text-input"
              type="text"
              value={textInput}
              onChange={e => setTextInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendMessage(textInput)}
              placeholder="Type your answer…"
              disabled={isLoading}
              className="w-full px-4 py-3 pr-12 rounded-xl border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm disabled:opacity-50"
            />
            <button
              id="chat-send-button"
              onClick={() => sendMessage(textInput)}
              disabled={!textInput.trim() || isLoading}
              className="absolute right-2 p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? <Loader2 size={17} className="animate-spin" /> : <Send size={17} />}
            </button>
          </div>
        </div>
      )}

      {/* Done state — schemes shown, no more input */}
      {isDone && (
        <div className="p-4 border-t border-slate-100 bg-gradient-to-r from-green-50 to-emerald-50 flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center flex-shrink-0">
            <Check size={16} className="text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-green-800">Intake complete!</p>
            <p className="text-xs text-green-600">Running full grant research pipeline…</p>
          </div>
          <Loader2 size={18} className="ml-auto text-green-600 animate-spin" />
        </div>
      )}
    </div>
  );
}
