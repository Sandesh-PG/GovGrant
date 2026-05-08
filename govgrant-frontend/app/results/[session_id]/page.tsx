'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shield, ArrowLeft, Download, Bell, ExternalLink, FileText, CheckCircle2 } from 'lucide-react';
import { GrantCard } from '@/components/GrantCard';
import { Checklist } from '@/components/Checklist';
import { CoverSummary } from '@/components/CoverSummary';
import { api } from '@/lib/api';
import { GrantReport } from '@/lib/types';

export default function ResultsPage({ params }: { params: { session_id: string } }) {
  const [report, setReport] = useState<GrantReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      router.push('/login');
      return;
    }

    const fetchResults = async () => {
      try {
        const data = await api.getResults(params.session_id);
        setReport(data);
      } catch (err) {
        console.error('Failed to fetch results', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchResults();
  }, [params.session_id, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-white flex flex-col items-center justify-center space-y-4">
        <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
        <p className="text-slate-500 font-medium">Fetching your grant report...</p>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="min-h-screen bg-white flex flex-col items-center justify-center space-y-4">
        <p className="text-slate-500 font-medium">Report not found.</p>
        <button onClick={() => router.push('/chat')} className="text-blue-600 font-bold hover:underline">
          Go back to chat
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="px-6 py-4 bg-white border-b border-slate-100 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center space-x-2">
          <Shield className="text-blue-600 w-5 h-5" />
          <span className="font-outfit font-bold text-lg text-slate-900">GovGrant</span>
        </div>
        
        <div className="flex items-center space-x-4">
          <button 
            onClick={() => window.print()}
            className="flex items-center text-sm font-semibold text-slate-600 hover:text-blue-600 transition-colors px-3 py-2 rounded-xl hover:bg-slate-50"
          >
            <Download size={16} className="mr-2" />
            PDF Report
          </button>
          <button 
            onClick={() => router.push(`/alerts?session_id=${params.session_id}`)}
            className="flex items-center px-4 py-2.5 bg-blue-600 text-white text-sm font-bold rounded-xl hover:bg-blue-700 transition-all shadow-lg shadow-blue-200"
          >
            <Bell size={16} className="mr-2" />
            Set Alerts
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto w-full p-6 md:p-12">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
          {/* Left Column: Grant Matches */}
          <div className="lg:col-span-2 space-y-8">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-outfit font-extrabold text-slate-900 tracking-tight mb-2">
                  Your top 5 grant matches
                </h1>
                <p className="text-slate-500 font-medium">
                  Based on your business profile and GEMINI AI analysis.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-6">
              {report.schemes.map((scheme, i) => (
                <GrantCard key={i} scheme={scheme} />
              ))}
            </div>
          </div>

          {/* Right Column: Docs & Summary */}
          <div className="space-y-8">
            <Checklist documents={report.documents} />
            
            <div className="bg-white border border-slate-100 rounded-2xl p-6 shadow-sm">
              <h3 className="text-lg font-bold text-slate-900 mb-6 flex items-center">
                Action Cards
              </h3>
              <div className="space-y-6">
                {report.action_cards.map((card, i) => (
                  <div key={i} className="space-y-3 pb-6 border-b border-slate-50 last:border-0 last:pb-0">
                    <div className="flex items-start justify-between">
                      <h4 className="text-sm font-bold text-slate-800">{card.scheme_name}</h4>
                      <span className="text-[10px] bg-blue-50 text-blue-600 px-2 py-0.5 rounded font-bold uppercase tracking-wider">
                        {card.estimated_days} Days Est.
                      </span>
                    </div>
                    <ul className="space-y-2">
                      {card.steps.slice(0, 3).map((step, si) => (
                        <li key={si} className="flex items-start text-xs text-slate-500">
                          <CheckCircle2 size={12} className="text-green-500 mr-2 flex-shrink-0 mt-0.5" />
                          {step}
                        </li>
                      ))}
                      {card.steps.length > 3 && (
                        <li className="text-[10px] text-blue-500 font-bold pl-5">
                          + {card.steps.length - 3} more steps in dashboard
                        </li>
                      )}
                    </ul>
                  </div>
                ))}
              </div>
            </div>

            <CoverSummary summary={report.cover_summary} />
          </div>
        </div>
      </main>
    </div>
  );
}
