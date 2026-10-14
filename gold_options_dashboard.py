def create_combined_chart(zero_gamma_level, distance_to_zero_gamma, setup_signal, gex_flow, zones, S):
    """إنشاء رسم Plotly واحد يجمع Zero-Gamma و Confluence Zones (قابل للحفظ كـ PNG واحد)"""
    fig = go.Figure()
    
    fig.update_xaxes(visible=False, range=[0, 1])
    fig.update_yaxes(visible=False, range=[0, 1])
    
    # ============ القسم العلوي: Zero-Gamma ============
    # عنوان القسم
    fig.add_annotation(
        x=0.5, y=0.94,
        text="<b>🎯 مؤشرات صفر غاما (Zero-Gamma)</b>",
        showarrow=False,
        font=dict(color="#00d4ff", size=16),
        xref="paper", yref="paper"
    )
    
    # القيم الأربع
    positions = [0.125, 0.375, 0.625, 0.875]
    titles = ["📍 مستوى صفر غاما", "📏 المسافة من السعر", "📈 الإشارة", "🌊 تدفق غاما"]
    values = [f"${zero_gamma_level:.2f}", f"${distance_to_zero_gamma:.2f}", setup_signal, f"{gex_flow:+.0f}"]
    colors = ["white", "white", "white", "limegreen" if gex_flow > 0 else "crimson"]
    
    for pos, title, value, color in zip(positions, titles, values, colors):
        fig.add_annotation(
            x=pos, y=0.82,
            text=f"<b>{title}</b>",
            showarrow=False,
            font=dict(color="white", size=11),
            xref="paper", yref="paper"
        )
        fig.add_annotation(
            x=pos, y=0.69,
            text=f"<b>{value}</b>",
            showarrow=False,
            font=dict(color=color, size=20),
            xref="paper", yref="paper"
        )
    
    # خط فاصل
    fig.add_shape(
        type="line",
        x0=0.05, x1=0.95, y0=0.58, y1=0.58,
        line=dict(color="#444", width=1)
    )
    
    # ============ القسم السفلي: Confluence Zones ============
    fig.add_annotation(
        x=0.5, y=0.48,
        text="<b>📍 مناطق التقاء غاما وفانا (Confluence Zones)</b>",
        showarrow=False,
        font=dict(color="#00d4ff", size=16),
        xref="paper", yref="paper"
    )
    
    # تجميع الرسائل
    lines = []
    colors_zones = []
    
    if zones:
        squeeze_zones = [z for z in zones if z['type'] == 'squeeze']
        meltdown_zones = [z for z in zones if z['type'] == 'meltdown']
        
        if squeeze_zones:
            squeeze_str = ', '.join([f"${z['strike']:.2f}" for z in squeeze_zones])
            lines.append(f"💥 مناطق Squeeze (صاعد) عند: {squeeze_str}")
            colors_zones.append("limegreen")
        
        if meltdown_zones:
            meltdown_str = ', '.join([f"${z['strike']:.2f}" for z in meltdown_zones])
            lines.append(f"⬇️ مناطق Meltdown (هابط) عند: {meltdown_str}")
            colors_zones.append("crimson")
        
        for zone in zones:
            if zone['type'] == 'squeeze' and S <= zero_gamma_level:
                lines.append(f"⚠️ Squeeze عند ${zone['strike']:.2f} غير مفعّل (السعر تحت صفر غاما)")
                colors_zones.append("orange")
            if zone['type'] == 'meltdown' and S >= zero_gamma_level:
                lines.append(f"⚠️ Meltdown عند ${zone['strike']:.2f} غير مفعّل (السعر فوق صفر غاما)")
                colors_zones.append("orange")
    
    if not lines:
        lines = ["لا توجد مناطق التقاء حالياً."]
        colors_zones = ["gray"]
    
    # عرض الرسائل
    start_y = 0.37
    step = 0.08
    
    for i, (line, color) in enumerate(zip(lines, colors_zones)):
        y_pos = start_y - (i * step)
        if y_pos < 0.05:
            break
        fig.add_annotation(
            x=0.5, y=y_pos,
            text=f"<b>{line}</b>",
            showarrow=False,
            font=dict(color=color, size=13),
            xref="paper", yref="paper"
        )
    
    # حساب الارتفاع ديناميكياً
    height = max(450, 250 + len(lines) * 40)
    
    fig.update_layout(
        plot_bgcolor="#111",
        paper_bgcolor="#222",
        height=height,
        margin=dict(l=10, r=10, t=20, b=20),
        showlegend=False
    )
    
    return fig
