'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shield, Loader2, Search, FileCheck, Award, Zap } from 'lucide-react';
import { AgentStatusCard } from '@/components/AgentStatusCard';
import { cn } from '@/components/StatusBadge';

type PipelineStatus = 'pending' | 'loading' | 'completed';

export default function ProcessingPage() {
  const [status, setStatus] = useState({
    intake: 'completed' as PipelineStatus,
    research: 'loading' as PipelineStatus,
    validation: 'pending' as PipelineStatus,
    report: 'pending' as PipelineStatus
  });
  const [message, setMessage] = useState('Searching 100+ government schemes...');
  const router = useRouter();

  useEffect(() => {
    const sessionId = localStorage.getItem('current_session_id');
    const token = localStorage.getItem('auth_token');
    if (!sessionId || !token) {
      router.push('/chat');
      return;
    }

    const runPipeline = async () => {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/pipeline`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            session_id: sessionId,
            message: "Analyze my profile and generate the report.",
            history: []
          })
        });

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No reader');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              const eventType = line.split('event: ')[1].split('\n')[0];
              const dataLine = lines[lines.indexOf(line) + 1] || '';
              const dataStr = dataLine.replace('data: ', '');
              const data = JSON.parse(dataStr);

              if (eventType === 'research_done') {
                setStatus(prev => ({ ...prev, research: 'completed', validation: 'loading' }));
                setMessage(`Found ${data.length} potential matching schemes...`);
              } else if (eventType === 'validation_done') {
                setStatus(prev => ({ ...prev, validation: 'completed', report: 'loading' }));
                setMessage('Ranking top 5 matches based on your profile...');
              } else if (eventType === 'report_ready') {
                setStatus(prev => ({ ...prev, report: 'completed' }));
                setMessage('Report finalized. Redirecting...');
                setTimeout(() => {
                  router.push(`/results/${sessionId}`);
                }, 1000);
              }
            }
          }
        }
      } catch (err) {
        console.error('Pipeline failed', err);
      }
    };

    runPipeline();
  }, [router]);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-xl space-y-12">
        <div className="text-center space-y-4">
          <div className="inline-flex p-4 bg-white rounded-3xl shadow-xl border border-slate-100 mb-4 animate-bounce">
            <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
          </div>
          <h1 className="text-3xl font-outfit font-extrabold text-slate-900 tracking-tight">
            Building your grant report
          </h1>
          <p className="text-slate-500 font-medium">
            {message}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4">
          <AgentStatusCard 
            name="Intake Agent" 
            description="Profile collected and verified" 
            status={status.intake} 
          />
          <AgentStatusCard 
            name="Research Agent" 
            description="Scanning 100+ state and central schemes" 
            status={status.research} 
          />
          <AgentStatusCard 
            name="Validator Agent" 
            description="Checking eligibility and scoring matches" 
            status={status.validation} 
          />
          <AgentStatusCard 
            name="Planner Agent" 
            description="Generating documents and action plan" 
            status={status.report} 
          />
        </div>

        <div className="bg-blue-600/5 rounded-2xl p-6 border border-blue-100 flex items-start">
          <Zap size={20} className="text-blue-600 mr-4 flex-shrink-0 mt-1" />
          <div className="text-sm">
            <p className="text-blue-900 font-bold mb-1">Did you know?</p>
            <p className="text-blue-700 leading-relaxed">
              GEMINI 2.0 FLASH is currently analyzing scheme PDFs from our database to find the most accurate matches for your sector.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
