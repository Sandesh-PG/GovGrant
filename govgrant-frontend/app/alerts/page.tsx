'use client';

import { useEffect, useState, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Shield, Bell, Mail, MessageSquare, Check, ArrowRight, Calendar, AlertCircle } from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/components/StatusBadge';

function AlertsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const sessionId = searchParams.get('session_id');
  
  const [email, setEmail] = useState('');
  const [whatsappEnabled, setWhatsappEnabled] = useState(false);
  const [phone, setPhone] = useState('');
  const [deadlines, setDeadlines] = useState<any[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    const userStr = localStorage.getItem('user');
    if (userStr) {
      const user = JSON.parse(userStr);
      setEmail(user.email);
    }

    if (sessionId) {
      api.getResults(sessionId).then(data => {
        const dls = data.schemes
          .filter(s => s.deadline && s.deadline !== 'Rolling')
          .map(s => ({
            name: s.scheme_name,
            date: s.deadline,
            rank: s.rank
          }));
        setDeadlines(dls);
      });
    }
  }, [sessionId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sessionId) return;
    
    setIsSubmitting(true);
    try {
      await api.createAlerts({
        session_id: sessionId,
        email,
        whatsapp_enabled: whatsappEnabled,
        phone: whatsappEnabled ? phone : undefined
      });
      setSuccess(true);
      setTimeout(() => router.push(`/results/${sessionId}`), 3000);
    } catch (err) {
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!sessionId) return <div className="p-12 text-center">Session not found</div>;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-lg bg-white border border-slate-100 rounded-3xl shadow-xl overflow-hidden">
        <div className="bg-slate-900 p-8 text-center text-white">
          <div className="inline-flex p-3 bg-white/10 rounded-2xl mb-4">
            <Bell className="w-8 h-8 text-blue-400" />
          </div>
          <h1 className="text-2xl font-bold font-outfit">Deadline Alerts</h1>
          <p className="text-slate-400 text-sm mt-2">Never miss a grant application window.</p>
        </div>

        {success ? (
          <div className="p-12 text-center space-y-4">
            <div className="w-16 h-16 bg-green-50 text-green-500 rounded-full flex items-center justify-center mx-auto mb-4">
              <Check size={32} />
            </div>
            <h2 className="text-xl font-bold text-slate-900">Alerts Activated!</h2>
            <p className="text-slate-500 text-sm">
              We&apos;ll notify you at 14 days and 3 days before each deadline.
            </p>
            <p className="text-xs text-slate-400 pt-4 animate-pulse">Redirecting to your report...</p>
          </div>
        ) : (
          <div className="p-8 space-y-8">
            <div className="space-y-4">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center">
                Upcoming Deadlines
              </h3>
              <div className="space-y-3">
                {deadlines.length > 0 ? deadlines.map((dl, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-100">
                    <div className="flex items-center">
                      <div className="w-6 h-6 bg-white border rounded-full flex items-center justify-center text-[10px] font-bold text-slate-400 mr-3">
                        {dl.rank}
                      </div>
                      <span className="text-sm font-semibold text-slate-700">{dl.name}</span>
                    </div>
                    <div className="flex items-center text-xs font-bold text-slate-900">
                      <Calendar size={14} className="mr-2 text-blue-500" />
                      {dl.date}
                    </div>
                  </div>
                )) : (
                  <div className="flex items-center p-3 bg-slate-50 rounded-xl border border-slate-100 text-sm text-slate-500 italic">
                    <AlertCircle size={14} className="mr-2" />
                    No fixed deadlines for these schemes.
                  </div>
                )}
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Notification Email</label>
                  <div className="relative">
                    <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      className="w-full pl-12 pr-4 py-3 bg-slate-50 border border-slate-100 rounded-2xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center">
                      <div className="w-10 h-10 bg-green-50 text-green-600 rounded-xl flex items-center justify-center mr-3">
                        <MessageSquare size={18} />
                      </div>
                      <div>
                        <p className="text-sm font-bold text-slate-800">WhatsApp Alerts</p>
                        <p className="text-[10px] text-slate-500 uppercase font-bold tracking-tight">Beta Feature</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setWhatsappEnabled(!whatsappEnabled)}
                      className={cn(
                        "w-12 h-6 rounded-full transition-colors relative",
                        whatsappEnabled ? "bg-green-500" : "bg-slate-200"
                      )}
                    >
                      <div className={cn(
                        "w-4 h-4 bg-white rounded-full absolute top-1 transition-all",
                        whatsappEnabled ? "left-7" : "left-1"
                      )} />
                    </button>
                  </div>

                  {whatsappEnabled && (
                    <div className="animate-in slide-in-from-top-2 fade-in duration-300">
                      <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Phone Number</label>
                      <input
                        type="tel"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        placeholder="+91 98765 43210"
                        required={whatsappEnabled}
                        className="w-full px-4 py-3 bg-slate-50 border border-slate-100 rounded-2xl focus:outline-none focus:ring-2 focus:ring-green-500"
                      />
                    </div>
                  )}
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full py-4 bg-blue-600 text-white font-bold rounded-2xl hover:bg-blue-700 transition-all flex items-center justify-center shadow-lg shadow-blue-100 disabled:bg-blue-300"
              >
                {isSubmitting ? <Loader2 className="animate-spin" /> : (
                  <>
                    Enable Notifications
                    <ArrowRight className="ml-2" size={18} />
                  </>
                )}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}

export default function AlertsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-50 flex items-center justify-center">Loading...</div>}>
      <AlertsContent />
    </Suspense>
  );
}
