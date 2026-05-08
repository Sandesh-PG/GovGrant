import Link from 'next/link';
import { ArrowRight, CheckCircle2, Shield, Zap, TrendingUp, Globe } from 'lucide-react';

export default function LandingPage() {
  return (
    <div className="flex flex-col min-h-screen">
      {/* Navbar */}
      <nav className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-white/80 backdrop-blur-md sticky top-0 z-50">
        <div className="flex items-center space-x-2">
          <div className="bg-blue-600 p-1.5 rounded-lg">
            <Shield className="text-white w-5 h-5" />
          </div>
          <span className="font-outfit font-bold text-xl tracking-tight text-slate-900">GovGrant</span>
        </div>
        <div className="flex items-center space-x-6">
          <Link href="/login" className="text-sm font-semibold text-slate-600 hover:text-blue-600 transition-colors">
            Sign In
          </Link>
          <Link href="/register" className="px-5 py-2.5 bg-blue-600 text-white text-sm font-bold rounded-xl hover:bg-blue-700 transition-all shadow-lg shadow-blue-200">
            Get Started
          </Link>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="px-6 pt-20 pb-32 max-w-7xl mx-auto text-center">
        <div className="inline-flex items-center px-4 py-2 bg-blue-50 text-blue-700 text-xs font-bold rounded-full mb-8 animate-fade-in">
          <Zap size={14} className="mr-2" />
          GEMINI 2.0 FLASH POWERED
        </div>
        <h1 className="font-outfit text-5xl md:text-7xl font-extrabold text-slate-900 tracking-tight leading-[1.1] mb-8">
          Find the government grants your business <span className="text-blue-600">actually qualifies for.</span>
        </h1>
        <p className="text-lg md:text-xl text-slate-500 max-w-3xl mx-auto mb-12 leading-relaxed">
          Answer 6 simple questions. Our AI scans 100+ state and central government schemes to find your top 5 matches in under 30 seconds.
        </p>
        <div className="flex flex-col md:flex-row items-center justify-center space-y-4 md:space-y-0 md:space-x-6">
          <Link href="/chat" className="w-full md:w-auto px-8 py-4 bg-slate-900 text-white text-lg font-bold rounded-2xl hover:bg-slate-800 transition-all flex items-center justify-center shadow-xl shadow-slate-200 group">
            Find your grants
            <ArrowRight className="ml-2 group-hover:translate-x-1 transition-transform" />
          </Link>
          <p className="text-sm text-slate-400 font-medium flex items-center">
            <CheckCircle2 size={16} className="text-green-500 mr-2" />
            No credit card required
          </p>
        </div>
      </section>

      {/* How it works */}
      <section className="bg-slate-50 py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <h2 className="font-outfit text-3xl font-bold text-center text-slate-900 mb-16">How it works</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
            {[
              { step: "01", title: "Tell us about your business", desc: "Briefly describe your sector, location, and what you need funding for." },
              { step: "02", title: "AI-Powered Search", desc: "We search 100+ government schemes including central and state subsidies." },
              { step: "03", title: "Actionable Report", desc: "Get a document checklist, application links, and a copy-ready cover summary." }
            ].map((item, i) => (
              <div key={i} className="relative p-8 bg-white rounded-3xl border border-slate-100 shadow-sm hover:shadow-md transition-all">
                <span className="absolute -top-6 left-8 text-6xl font-outfit font-black text-blue-600/10 select-none">{item.step}</span>
                <h3 className="text-xl font-bold text-slate-900 mt-4 mb-3">{item.title}</h3>
                <p className="text-slate-500 text-sm leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust Stats */}
      <section className="py-24 px-6 max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            { icon: <Globe className="text-blue-500" />, title: "100+ Schemes Tracked", desc: "Always up to date with the latest gazette notifications." },
            { icon: <Zap className="text-amber-500" />, title: "State + Central", desc: "Complete coverage of Maharashtra, Karnataka, Tamil Nadu & more." },
            { icon: <TrendingUp className="text-green-500" />, title: "Free to use", desc: "We believe in empowering MSMEs without hidden fees." }
          ].map((item, i) => (
            <div key={i} className="flex flex-col items-center text-center p-8">
              <div className="mb-6 p-4 bg-slate-50 rounded-2xl">{item.icon}</div>
              <h4 className="text-lg font-bold text-slate-900 mb-2">{item.title}</h4>
              <p className="text-slate-500 text-sm">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-auto py-12 px-6 border-t border-slate-100">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center space-y-4 md:space-y-0">
          <div className="flex items-center space-x-2">
            <Shield className="text-blue-600 w-5 h-5" />
            <span className="font-outfit font-bold text-lg text-slate-900">GovGrant</span>
          </div>
          <p className="text-sm text-slate-400">© 2024 GovGrant — Empowering Indian MSMEs through technology.</p>
          <div className="flex space-x-6 text-sm font-medium text-slate-500">
            <Link href="#" className="hover:text-blue-600">Privacy</Link>
            <Link href="#" className="hover:text-blue-600">Terms</Link>
            <Link href="#" className="hover:text-blue-600">Contact</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
