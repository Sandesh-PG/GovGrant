'use client';

import { useEffect, useState, use } from 'react';
import { useRouter } from 'next/navigation';
import { 
  Shield, ArrowLeft, Download, Bell, Sparkles, 
  CheckCircle2, Info, ChevronRight, FileCheck 
} from 'lucide-react';
import { GrantCard } from '@/components/GrantCard';
import { CoverSummary } from '@/components/CoverSummary';
import { api } from '@/lib/api';
import { GrantReport, SchemeDocuments, ActionCard } from '@/lib/types';

export default function ResultsPage({ params }: { params: Promise<{ session_id: string }> }) {
  const { session_id } = use(params);
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
        const data = await api.getResults(session_id);
        setReport(data);
      } catch (err) {
        console.error('Failed to fetch results', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchResults();
  }, [session_id, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#fafbfc] flex flex-col items-center justify-center space-y-6">
        <div className="relative">
          <div className="w-16 h-16 border-4 border-blue-600/10 rounded-full"></div>
          <div className="absolute top-0 left-0 w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
        </div>
        <div className="text-center">
          <p className="text-slate-900 font-black text-xl mb-1">Building your report...</p>
          <p className="text-slate-500 font-medium">Finalizing grant eligibility scores</p>
        </div>
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

  // Helper to find docs for a specific scheme
  const getDocsForScheme = (schemeName: string) => {
    const group = report.documents_by_scheme?.find(
      (g: SchemeDocuments) => g.scheme_name.toLowerCase() === schemeName.toLowerCase()
    );
    return group?.documents || [];
  };

  // Helper to find action card for a specific scheme
  const getActionCardForScheme = (schemeName: string) => {
    return report.action_cards.find(
      (c: ActionCard) => c.scheme_name.toLowerCase() === schemeName.toLowerCase()
    );
  };

  return (
    <div className="min-h-screen bg-[#fafbfc] flex flex-col selection:bg-blue-500/30">
      {/* Premium Header */}
      <header className="px-6 md:px-12 py-5 bg-white/80 border-b border-slate-100 flex items-center justify-between sticky top-0 z-50 backdrop-blur-xl">
        <div className="flex items-center space-x-6">
          <button
            onClick={() => router.push('/')}
            className="flex items-center text-sm font-black text-slate-400 hover:text-blue-600 transition-colors uppercase tracking-widest"
          >
            <ArrowLeft size={16} className="mr-2" />
            Home
          </button>
          <div className="w-px h-6 bg-slate-100" />
          <div className="flex items-center space-x-2 cursor-pointer" onClick={() => router.push('/')}>
            <div className="bg-blue-600 p-1.5 rounded-lg">
              <Shield className="text-white w-4 h-4" />
            </div>
            <span className="font-outfit font-black text-xl text-slate-900">GovGrant</span>
          </div>
        </div>
        
        <div className="flex items-center space-x-4">
          <button 
            onClick={() => window.print()}
            className="hidden md:flex items-center text-sm font-black text-slate-500 hover:text-slate-900 transition-colors px-4 py-2"
          >
            <Download size={16} className="mr-2" />
            Download PDF
          </button>
          <button 
            onClick={() => router.push('/chat')}
            className="px-6 py-2.5 bg-slate-900 text-white text-sm font-black rounded-xl hover:bg-blue-600 transition-all shadow-lg active:scale-95"
          >
            New Discovery
          </button>
          <button 
            className="p-2.5 bg-blue-50 text-blue-600 rounded-xl hover:bg-blue-100 transition-colors"
            title="Set Alerts"
          >
            <Bell size={20} />
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto w-full px-6 py-12 md:py-20">
        {/* Intro Section */}
        <div className="mb-16 text-center">
          <div className="inline-flex items-center px-4 py-1.5 bg-blue-50 rounded-full mb-6 border border-blue-100">
            <Sparkles size={14} className="text-blue-600 mr-2" />
            <span className="text-[10px] font-black tracking-widest uppercase text-blue-600">
              Analysis Complete
            </span>
          </div>
          <h1 className="text-4xl md:text-6xl font-outfit font-black text-slate-900 tracking-tighter mb-6 leading-none">
            Your Personalized <br />Grant Report
          </h1>
          <p className="text-slate-500 text-xl font-medium max-w-2xl mx-auto leading-relaxed">
            We analyzed 100+ schemes. Based on your MSME profile, these 5 offer the highest probability of successful funding.
          </p>
        </div>

        {/* Global Business Summary Section */}
        <div className="mb-20">
           <CoverSummary summary={report.cover_summary} />
        </div>

        {/* The Schemes List - Now Full Width & Self-Contained */}
        <div className="space-y-10">
          <div className="flex items-center justify-between mb-8">
             <div className="flex items-center space-x-3">
               <div className="w-10 h-10 rounded-xl bg-slate-900 text-white flex items-center justify-center font-black">
                 <FileCheck size={20} />
               </div>
               <h2 className="text-2xl font-black text-slate-900 tracking-tight">Top 5 Matches</h2>
             </div>
             <div className="hidden sm:flex items-center text-xs font-black text-slate-400 uppercase tracking-widest">
               Expand cards for requirements <ChevronRight size={14} className="ml-1" />
             </div>
          </div>

          <div className="grid grid-cols-1 gap-8">
            {report.schemes.map((scheme, i) => (
              <GrantCard 
                key={i} 
                scheme={scheme} 
                documents={getDocsForScheme(scheme.scheme_name)}
                actionCard={getActionCardForScheme(scheme.scheme_name)}
              />
            ))}
          </div>
        </div>

        {/* Footer Disclaimer */}
        <div className="mt-24 p-8 glass rounded-[2.5rem] border border-slate-100 text-center">
           <Info className="mx-auto text-blue-500 mb-4" />
           <p className="text-sm text-slate-400 font-medium leading-relaxed max-w-2xl mx-auto italic">
             Disclaimer: Eligibility scores are AI-calculated estimates. Requirements are subject to change by respective government departments. Always verify details on the official portal before applying.
           </p>
        </div>
      </main>
    </div>
  );
}
