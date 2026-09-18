import React, { useState } from 'react';
import {
  RotateCcw,
  ArrowLeft,
  ArrowRight,
  Lock,
  Search,
  ShoppingCart,
  Headphones,
  Home,
  Watch,
  Laptop,
  Box,
  CheckCircle2,
  Square,
  Sparkles,
  Star,
  ExternalLink
} from 'lucide-react';

export const BrowserSurface: React.FC = () => {
  const [url, setUrl] = useState('https://shop.aetherius.com/category/audio');
  const [selectedCategory, setSelectedCategory] = useState('Audio & Headphones');
  const [isAutomating, setIsAutomating] = useState(true);

  const categories = [
    { name: 'Audio & Headphones', icon: Headphones, active: true },
    { name: 'Smart Home', icon: Home },
    { name: 'Wearables', icon: Watch },
    { name: 'Computing', icon: Laptop },
    { name: 'Accessories', icon: Box },
  ];

  const products = [
    {
      id: 'p1',
      title: 'Aetherius Spatial X9',
      price: '$189.99',
      originalPrice: '$229.99',
      rating: 4.8,
      reviews: 1420,
      tag: 'Best Value',
      tagColor: 'bg-blue-600',
      battery: '40h ANC',
      image: 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&auto=format&fit=crop&q=80',
    },
    {
      id: 'p2',
      title: 'SoundNova QuietMax 2',
      price: '$149.00',
      rating: 4.6,
      reviews: 890,
      battery: '32h Playtime',
      image: 'https://images.unsplash.com/photo-1583394838336-acd977736f90?w=500&auto=format&fit=crop&q=80',
    },
    {
      id: 'p3',
      title: 'AeroBeat Wireless Studio',
      price: '$179.99',
      originalPrice: '$219.99',
      rating: 4.7,
      reviews: 620,
      tag: '-20%',
      tagColor: 'bg-rose-600',
      battery: '50h Battery',
      image: 'https://images.unsplash.com/photo-1484704849700-f032a568e944?w=500&auto=format&fit=crop&q=80',
    },
    {
      id: 'p4',
      title: 'ZenWave Pure Sound ANC',
      price: '$199.00',
      rating: 4.9,
      reviews: 2150,
      tag: 'Top Rated',
      tagColor: 'bg-emerald-600',
      battery: '45h ANC',
      image: 'https://images.unsplash.com/photo-1546435770-a3e426bf472b?w=500&auto=format&fit=crop&q=80',
    },
  ];

  return (
    <div className="flex-1 flex flex-col h-full bg-[#070b14] text-slate-100 overflow-hidden">
      {/* Browser Chrome Header */}
      <div className="h-11 bg-slate-950/90 border-b border-slate-800/80 px-3 flex items-center justify-between text-xs shrink-0 select-none">
        <div className="flex items-center gap-2">
          <button className="p-1 text-slate-500 hover:text-slate-300">
            <ArrowLeft className="w-3.5 h-3.5" />
          </button>
          <button className="p-1 text-slate-500 hover:text-slate-300">
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
          <button className="p-1 text-slate-400 hover:text-slate-200">
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* URL Pill */}
        <div className="flex-1 max-w-lg mx-3">
          <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-slate-900 border border-slate-800 text-[11px] text-slate-300 font-mono">
            <Lock className="w-3 h-3 text-emerald-400" />
            <span className="text-emerald-400 font-medium">https://</span>
            <span className="text-slate-200">shop.aetherius.com</span>
            <span className="text-slate-500">/category/audio</span>
          </div>
        </div>

        <div className="flex items-center gap-2 text-slate-400 text-xs">
          <span className="flex items-center gap-1 text-[11px] bg-cyan-950/50 border border-cyan-500/30 text-cyan-300 px-2 py-0.5 rounded-full">
            <Sparkles className="w-3 h-3 text-cyan-400" />
            Puppeteer Sandbox
          </span>
        </div>
      </div>

      {/* Embedded Web Page */}
      <div className="flex-1 overflow-y-auto bg-slate-950">
        {/* Store Navigation */}
        <nav className="h-14 border-b border-slate-800/80 px-6 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2 font-bold text-sm text-white">
              <div className="w-6 h-6 rounded-lg bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center">
                <Sparkles className="w-3.5 h-3.5 text-white" />
              </div>
              <span>Aetherius Shop</span>
            </div>
            <div className="hidden sm:flex items-center gap-4 text-xs text-slate-300 font-medium">
              <span className="text-cyan-400">Products</span>
              <span className="hover:text-white cursor-pointer">Categories</span>
              <span className="hover:text-white cursor-pointer">Deals</span>
              <span className="hover:text-white cursor-pointer">Support</span>
            </div>
          </div>

          <div className="flex items-center gap-3 text-slate-400">
            <Search className="w-4 h-4 cursor-pointer hover:text-slate-200" />
            <div className="relative">
              <ShoppingCart className="w-4 h-4 cursor-pointer hover:text-slate-200" />
              <span className="absolute -top-1.5 -right-2 w-4 h-4 rounded-full bg-blue-600 text-white text-[9px] font-bold flex items-center justify-center">
                3
              </span>
            </div>
          </div>
        </nav>

        {/* Hero Section */}
        <div className="relative mx-6 my-5 rounded-2xl overflow-hidden bg-gradient-to-r from-blue-950 via-slate-900 to-indigo-950 border border-slate-800 p-6 sm:p-8 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="max-w-md space-y-3 z-10">
            <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/30">
              Autumn Audio Collection
            </span>
            <h1 className="text-2xl sm:text-3xl font-black text-white leading-tight">
              Elevate Everyday Living
            </h1>
            <p className="text-xs text-slate-300">
              Thoughtful tech for a brighter tomorrow. High fidelity acoustics with adaptive noise cancellation.
            </p>
            <button className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-lg transition-all">
              Shop Now →
            </button>
          </div>

          <div className="relative w-48 h-48 sm:w-56 sm:h-56 shrink-0">
            <img
              src="https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&auto=format&fit=crop&q=80"
              alt="Headphones"
              className="w-full h-full object-contain filter drop-shadow-[0_15px_25px_rgba(0,0,0,0.8)]"
            />
          </div>
        </div>

        {/* Category Selector */}
        <div className="px-6 py-2">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold text-slate-300">Shop by Category</h3>
            <span className="text-[11px] text-blue-400 cursor-pointer">View all →</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {categories.map((cat) => {
              const Icon = cat.icon;
              const isSelected = selectedCategory === cat.name;
              return (
                <button
                  key={cat.name}
                  onClick={() => setSelectedCategory(cat.name)}
                  className={`p-3 rounded-xl border flex flex-col items-center gap-2 transition-all ${
                    isSelected
                      ? 'bg-blue-600/15 border-blue-500/50 text-white shadow-md'
                      : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:bg-slate-900'
                  }`}
                >
                  <Icon className={`w-5 h-5 ${isSelected ? 'text-blue-400' : 'text-slate-400'}`} />
                  <span className="text-[11px] font-semibold text-center">{cat.name}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Featured Products under $200 */}
        <div className="px-6 py-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-slate-200">
              Target Results: Wireless Headphones under $200
            </h3>
            <span className="text-[11px] text-slate-400 font-mono">Found 4 matches</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {products.map((item) => (
              <div
                key={item.id}
                className="bg-slate-900/70 border border-slate-800 hover:border-slate-700 rounded-xl p-3.5 space-y-3 relative group transition-all"
              >
                {item.tag && (
                  <span
                    className={`absolute top-2.5 left-2.5 text-[9px] font-bold text-white px-2 py-0.5 rounded-full ${item.tagColor}`}
                  >
                    {item.tag}
                  </span>
                )}

                <div className="w-full h-32 rounded-lg overflow-hidden bg-slate-950 flex items-center justify-center p-2">
                  <img
                    src={item.image}
                    alt={item.title}
                    className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-300"
                  />
                </div>

                <div>
                  <h4 className="text-xs font-bold text-white line-clamp-1">{item.title}</h4>
                  <div className="flex items-center gap-1.5 mt-1">
                    <div className="flex items-center text-amber-400">
                      <Star className="w-3 h-3 fill-current" />
                      <span className="text-[11px] ml-1 font-semibold">{item.rating}</span>
                    </div>
                    <span className="text-[10px] text-slate-500">({item.reviews})</span>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1 border-t border-slate-800">
                  <div className="font-bold text-xs text-white">
                    {item.price}
                    {item.originalPrice && (
                      <span className="text-[10px] text-slate-500 line-through ml-1.5 font-normal">
                        {item.originalPrice}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-cyan-400 font-mono">{item.battery}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Live Automation Bar (matching Screenshot 1) */}
      <div className="p-3 bg-slate-950 border-t border-slate-800 shrink-0">
        <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
            <div>
              <div className="text-xs font-bold text-white">Browser Automation Running</div>
              <div className="text-[10px] text-slate-400">
                Navigating and extracting wireless headphone specifications...
              </div>
            </div>
          </div>

          <button
            onClick={() => setIsAutomating(!isAutomating)}
            className="flex items-center gap-1 px-3 py-1 rounded-lg bg-rose-600/20 text-rose-400 border border-rose-500/30 text-xs font-semibold hover:bg-rose-600/30 transition-colors"
          >
            <Square className="w-3 h-3 fill-current" />
            <span>Stop</span>
          </button>
        </div>

        {/* Live checklist steps */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 pt-2 text-[11px] font-mono">
          <div className="flex items-center justify-between text-emerald-400">
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="w-3 h-3" />
              <span>Opened https://shop.aetherius.com</span>
            </span>
            <span className="text-slate-500">10:28 AM</span>
          </div>

          <div className="flex items-center justify-between text-emerald-400">
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="w-3 h-3" />
              <span>Navigated to Audio & Headphones category</span>
            </span>
            <span className="text-slate-500">10:28 AM</span>
          </div>

          <div className="flex items-center justify-between text-cyan-300">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full border border-cyan-400 border-t-transparent animate-spin" />
              <span>Searching for products under $200...</span>
            </span>
            <span className="text-slate-500">10:28 AM</span>
          </div>

          <div className="flex items-center justify-between text-slate-500">
            <span>Extracting product details & reviews</span>
            <span>Pending</span>
          </div>
        </div>
      </div>
    </div>
  );
};
