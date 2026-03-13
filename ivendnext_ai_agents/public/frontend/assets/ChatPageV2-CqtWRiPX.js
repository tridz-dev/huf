import{j as n,a1 as Xs,F as Pr,bw as Ed,M as bd,Q as Dt,W as Or,aA as _d,a_ as Ad,bx as yd,am as Td,by as xd,aw as wd,a5 as Vn,a4 as Gn,ad as Kn,bz as Sd,R as Id,bA as Ur,P as kd,Y as $r,bB as Md,c as Cd,T as Ld,e as Rd,d as Hr,O as Dd,f as Nd,ab as Pd,aW as Od,aV as Ud,bC as $d,bD as jr,bE as Hd,b9 as jd,L as Fd,bF as Wd,bG as Bd,bH as Vd,aq as Gd}from"./ui-C_bZaD0H.js";import{r as h,u as Ni,f as ja,L as Zs,e as Fr,c as V}from"./vendor-CsIv5cG4.js";import{H as Kd,g as P,m as Wr,u as Js,B as ke,t as be,L as zd,N as qd,O as Yd,P as Qd,Q as Br,V as Xd,W as Zd,X as Jd,Y as ec,Z as tc,_ as ic,$ as ac,a0 as sc,a1 as nc,a2 as rc,a3 as oc,a4 as lc,a5 as dc,j as cc,a6 as uc,S as Ie,a7 as Es,a8 as Fa,f as Vr,a9 as hc,aa as mc,ab as pc,ac as zn,ad as fc,ae as Gr,af as vc,ag as gc,ah as Ec,ai as qn,aj as bc,ak as _c,al as Ac,am as yc}from"./index-iEjWaxPQ.js";import{T as Tc,a as xc,b as wc,c as Yn}from"./tabs-HSXc2Me6.js";import{c as Sc,b as Ic,a as kc,A as Mc,R as Cc,C as Lc,d as Rc}from"./accordion-B_-feLac.js";import{C as Dc,a as Nc,b as Pc,c as Oc,d as Uc,e as $c}from"./command-WuD-Jmma.js";import{D as Hc,f as jc,a as Fc,c as Wc}from"./dialog-DXWOUk0i.js";import{l as Bc,d as Si}from"./agentApi-cqmtvA3B.js";import{c as Vc,a as Gc,h as Kc,M as Qn,p as zc,b as qc,d as Yc,J as Qc,W as Xc,A as Zc,B as Jc,e as Pi,f as eu,g as tu}from"./jsxPreviewParser-CwNpAZbx.js";import{B as iu}from"./badge-G35hje98.js";import{C as bs}from"./code-block-WBwao0Or.js";import{T as Kr}from"./textarea-DOA0QBZb.js";import"./markdown-BWj_dXXt.js";import"./xyflow-Cf6NznGc.js";import"./card-CL-8IbMI.js";import"./mermaid-VLURNSYL-B3DD9FfA.js";import"./recharts-f7r3OYH5.js";import"./highlighter-8EDBHuXs.js";const au=Wr("",{variants:{variant:{listing_ai:"h-6 w-6 text-[10px] rounded-lg flex items-center justify-center text-white font-semibold shadow-inner",chat_ai:"h-8 w-8 text-xs rounded-lg flex items-center justify-center text-white font-semibold shadow-inner",chat_user:"h-8 w-8 rounded-full bg-gradient-to-tr from-orange-400 to-pink-600 border border-white/10 flex items-center justify-center text-[10px] font-bold text-white shadow-sm"}},defaultVariants:{variant:"chat_ai"}});function Zt({children:t,className:e,variant:i,color:a,...s}){const r=a&&(i==="listing_ai"||i==="chat_ai")?{backgroundColor:a}:void 0,o=!a&&(i==="listing_ai"||i==="chat_ai")?"bg-transparent":"";return n.jsx(Kd,{className:P(au({variant:i,className:`static ${e}`}),o),style:r,...s,children:t})}function Jt(t){const e=t.trim();return e&&e.split(/\s+/).filter(Boolean).slice(0,2).map(s=>{var r;return(r=s[0])==null?void 0:r.toUpperCase()}).join("")||"?"}const su=t=>n.jsx(Hc,{...t}),nu=t=>n.jsx(jc,{...t}),ru=({className:t,children:e,title:i="Model Selector",searchValue:a,onSearchChange:s,shouldFilter:r=!0,...o})=>{const l=r?{value:a,onValueChange:s,shouldFilter:!0}:{shouldFilter:!1,filter:()=>1};return n.jsxs(Fc,{className:P("p-0",t),...o,children:[n.jsx(Wc,{className:"sr-only",children:i}),n.jsx(Dc,{className:"**:data-[slot=command-input-wrapper]:h-auto",...l,children:e})]})},ou=({className:t,searchValue:e,onSearchChange:i,...a})=>n.jsx(Nc,{className:P("h-auto py-3.5",t),value:e,onValueChange:i,...a}),lu=t=>n.jsx(Pc,{...t}),du=t=>n.jsx(Oc,{...t}),cu=t=>n.jsx(Uc,{...t}),uu=t=>n.jsx($c,{...t}),Xn=({provider:t,className:e,...i})=>n.jsx("img",{...i,alt:`${t} logo`,className:P("size-3 dark:invert",e),height:12,src:`https://models.dev/logos/${t}.svg`,width:12}),hu=({className:t,...e})=>n.jsx("div",{className:P("-space-x-1 flex shrink-0 items-center [&>img]:rounded-full [&>img]:bg-background [&>img]:p-px [&>img]:ring-1 dark:[&>img]:bg-foreground",t),...e}),mu=({className:t,...e})=>n.jsx("span",{className:P("flex-1 truncate text-left",t),...e});function zr({value:t,onValueChange:e,disabled:i,showLabel:a=!1}){const[s,r]=h.useState(!1),o=h.useRef(!0),{items:l,initialLoading:c,search:p,setSearch:u}=Js({fetchFn:async m=>{const v=await Bc({page:m.page,limit:m.limit,start:m.start,search:m.search});return{data:v.items,hasMore:v.hasMore,total:v.total}},initialParams:{},pageSize:20,debounceMs:300,autoLoad:!0,autoLoadMore:!1});h.useEffect(()=>{(l.length>0&&!t&&o.current||l.length>0&&t)&&(o.current=!1)},[l,t]),h.useEffect(()=>{s&&u("")},[s,u]);const E=l.reduce((m,v)=>{const g=v.chef||"Other";return m[g]||(m[g]=[]),m[g].push(v),m},{});return n.jsxs(su,{onOpenChange:r,open:s,children:[n.jsx(nu,{asChild:!0,children:n.jsxs(ke,{size:a?"default":"icon",variant:a?"outline":"ghost",disabled:i,className:P("text-zinc-500 hover:bg-zinc-200 hover:text-zinc-900",a&&"gap-2",i&&"disabled:opacity-100"),children:[n.jsx(Xs,{className:a?"w-4 h-4":"w-5 h-5"}),a&&n.jsx("span",{children:"Select Agent"})]})}),n.jsxs(ru,{shouldFilter:!1,className:"min-h-[40%]",children:[n.jsx(ou,{placeholder:"Search models...",searchValue:p,onSearchChange:u}),n.jsx(lu,{children:c?n.jsx("div",{className:"p-4 text-center text-sm text-muted-foreground",children:"Loading models..."}):l.length===0?n.jsx(du,{children:"No models found."}):Object.entries(E).map(([m,v])=>n.jsx(cu,{heading:m,children:v.map(g=>n.jsxs(uu,{onSelect:()=>{e(g.id),r(!1)},value:g.id,children:[g.chefSlug&&n.jsx(Xn,{provider:g.chefSlug}),n.jsx(mu,{children:g.name}),n.jsx(hu,{children:g.providers.map(_=>n.jsx(Xn,{provider:_},_))}),t===g.id?n.jsx(Pr,{className:"ml-auto size-4"}):n.jsx("div",{className:"ml-auto size-4"})]},g.id))},m))})]})]})}const pu=Wr("px-1 w-full font-medium truncate text-zinc-900 bg-transparent outline-none focus-visible:ring-1 focus-visible:ring-primary rounded-sm cursor-pointer",{variants:{variant:{agent_list:"text-xs",recents_list:"text-sm block"}}}),qr=h.forwardRef(function({variant:e,value:i,conversationId:a},s){const[r,o]=h.useState(!1),l=h.useRef(null),c=h.useRef(!1),p=h.useRef(null);function u(T){!r&&!c.current&&T.preventDefault()}function E(){p.current&&(clearTimeout(p.current),p.current=null),c.current&&l.current&&(l.current.readOnly=!1)}function m(){c.current=!1,o(T=>!T),setTimeout(()=>{var T;return(T=l==null?void 0:l.current)==null?void 0:T.focus()},0)}function v(){p.current&&(clearTimeout(p.current),p.current=null),c.current=!0,o(!0),requestAnimationFrame(()=>{requestAnimationFrame(()=>{l!=null&&l.current&&(l.current.readOnly=!1,setTimeout(()=>{l!=null&&l.current&&c.current&&(l.current.focus(),l.current.select())},10),setTimeout(()=>{c.current=!1},100))})})}h.useImperativeHandle(s,()=>({activateInput:v}));function g(){l!=null&&l.current&&(l.current.value=i)}function _(T){if(c.current){p.current=setTimeout(()=>{c.current&&l.current&&l.current.focus()},10);return}if(o(!1),!T.target.value){be.error("Title cannot be empty!"),g();return}T.target.value!==i&&(b(T.target.value),l.current&&l.current.scrollTo({left:0}))}function A(T){var S;T.key=="Enter"&&r&&(l!=null&&l.current)&&(l==null?void 0:l.current.value)!=i&&l.current.blur(),T.key=="Escape"&&r&&(g(),(S=l.current)==null||S.blur(),o(!1))}async function b(T){try{await zd(a,T),be.success("Conversation title updated")}catch(S){be.error("Failed to update conversation title",{description:S instanceof Error?S.message:"An error occurred"}),g()}}return n.jsx("input",{ref:l,className:P(pu({variant:e})),defaultValue:i,readOnly:!r,onDoubleClick:m,onMouseDown:u,onFocus:E,onKeyDown:A,onBlur:_})});var en="ContextMenu",[fu]=Or(en,[Br]),ye=Br(),[vu,Yr]=fu(en),Qr=t=>{const{__scopeContextMenu:e,children:i,onOpenChange:a,dir:s,modal:r=!0}=t,[o,l]=h.useState(!1),c=ye(e),p=Ed(a),u=h.useCallback(E=>{l(E),p(E)},[p]);return n.jsx(vu,{scope:e,open:o,onOpenChange:u,modal:r,children:n.jsx(qd,{...c,dir:s,open:o,onOpenChange:u,modal:r,children:i})})};Qr.displayName=en;var Xr="ContextMenuTrigger",Zr=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,disabled:a=!1,...s}=t,r=Yr(Xr,i),o=ye(i),l=h.useRef({x:0,y:0}),c=h.useRef({getBoundingClientRect:()=>DOMRect.fromRect({width:0,height:0,...l.current})}),p=h.useRef(0),u=h.useCallback(()=>window.clearTimeout(p.current),[]),E=m=>{l.current={x:m.clientX,y:m.clientY},r.onOpenChange(!0)};return h.useEffect(()=>u,[u]),h.useEffect(()=>void(a&&u()),[a,u]),n.jsxs(n.Fragment,{children:[n.jsx(Yd,{...o,virtualRef:c}),n.jsx(bd.span,{"data-state":r.open?"open":"closed","data-disabled":a?"":void 0,...s,ref:e,style:{WebkitTouchCallout:"none",...t.style},onContextMenu:a?t.onContextMenu:Dt(t.onContextMenu,m=>{u(),E(m),m.preventDefault()}),onPointerDown:a?t.onPointerDown:Dt(t.onPointerDown,Hi(m=>{u(),p.current=window.setTimeout(()=>E(m),700)})),onPointerMove:a?t.onPointerMove:Dt(t.onPointerMove,Hi(u)),onPointerCancel:a?t.onPointerCancel:Dt(t.onPointerCancel,Hi(u)),onPointerUp:a?t.onPointerUp:Dt(t.onPointerUp,Hi(u))})]})});Zr.displayName=Xr;var gu="ContextMenuPortal",Jr=t=>{const{__scopeContextMenu:e,...i}=t,a=ye(e);return n.jsx(Xd,{...a,...i})};Jr.displayName=gu;var eo="ContextMenuContent",to=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,...a}=t,s=Yr(eo,i),r=ye(i),o=h.useRef(!1);return n.jsx(Zd,{...r,...a,ref:e,side:"right",sideOffset:2,align:"start",onCloseAutoFocus:l=>{var c;(c=t.onCloseAutoFocus)==null||c.call(t,l),!l.defaultPrevented&&o.current&&l.preventDefault(),o.current=!1},onInteractOutside:l=>{var c;(c=t.onInteractOutside)==null||c.call(t,l),!l.defaultPrevented&&!s.modal&&(o.current=!0)},style:{...t.style,"--radix-context-menu-content-transform-origin":"var(--radix-popper-transform-origin)","--radix-context-menu-content-available-width":"var(--radix-popper-available-width)","--radix-context-menu-content-available-height":"var(--radix-popper-available-height)","--radix-context-menu-trigger-width":"var(--radix-popper-anchor-width)","--radix-context-menu-trigger-height":"var(--radix-popper-anchor-height)"}})});to.displayName=eo;var Eu="ContextMenuGroup",io=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,...a}=t,s=ye(i);return n.jsx(Qd,{...s,...a,ref:e})});io.displayName=Eu;var bu="ContextMenuLabel",ao=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,...a}=t,s=ye(i);return n.jsx(ec,{...s,...a,ref:e})});ao.displayName=bu;var _u="ContextMenuItem",so=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,...a}=t,s=ye(i);return n.jsx(Jd,{...s,...a,ref:e})});so.displayName=_u;var Au="ContextMenuCheckboxItem",no=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,...a}=t,s=ye(i);return n.jsx(tc,{...s,...a,ref:e})});no.displayName=Au;var yu="ContextMenuRadioGroup",Tu=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,...a}=t,s=ye(i);return n.jsx(ic,{...s,...a,ref:e})});Tu.displayName=yu;var xu="ContextMenuRadioItem",ro=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,...a}=t,s=ye(i);return n.jsx(ac,{...s,...a,ref:e})});ro.displayName=xu;var wu="ContextMenuItemIndicator",oo=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,...a}=t,s=ye(i);return n.jsx(sc,{...s,...a,ref:e})});oo.displayName=wu;var Su="ContextMenuSeparator",lo=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,...a}=t,s=ye(i);return n.jsx(nc,{...s,...a,ref:e})});lo.displayName=Su;var Iu="ContextMenuArrow",ku=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,...a}=t,s=ye(i);return n.jsx(rc,{...s,...a,ref:e})});ku.displayName=Iu;var Mu="ContextMenuSubTrigger",co=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,...a}=t,s=ye(i);return n.jsx(oc,{...s,...a,ref:e})});co.displayName=Mu;var Cu="ContextMenuSubContent",uo=h.forwardRef((t,e)=>{const{__scopeContextMenu:i,...a}=t,s=ye(i);return n.jsx(lc,{...s,...a,ref:e,style:{...t.style,"--radix-context-menu-content-transform-origin":"var(--radix-popper-transform-origin)","--radix-context-menu-content-available-width":"var(--radix-popper-available-width)","--radix-context-menu-content-available-height":"var(--radix-popper-available-height)","--radix-context-menu-trigger-width":"var(--radix-popper-anchor-width)","--radix-context-menu-trigger-height":"var(--radix-popper-anchor-height)"}})});uo.displayName=Cu;function Hi(t){return e=>e.pointerType!=="mouse"?t(e):void 0}var Lu=Qr,Ru=Zr,Du=Jr,ho=to,Nu=io,mo=ao,po=so,fo=no,vo=ro,go=oo,Eo=lo,bo=co,_o=uo;const Pu=Lu,Ou=Ru,Uu=Nu,$u=h.forwardRef(({className:t,inset:e,children:i,...a},s)=>n.jsxs(bo,{ref:s,className:P("flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[state=open]:bg-accent data-[state=open]:text-accent-foreground",e&&"pl-8",t),...a,children:[i,n.jsx(dc,{className:"ml-auto h-4 w-4"})]}));$u.displayName=bo.displayName;const Hu=h.forwardRef(({className:t,...e},i)=>n.jsx(_o,{ref:i,className:P("z-50 min-w-[8rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2",t),...e}));Hu.displayName=_o.displayName;const Ao=h.forwardRef(({className:t,...e},i)=>n.jsx(Du,{children:n.jsx(ho,{ref:i,className:P("z-50 min-w-[8rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2",t),...e})}));Ao.displayName=ho.displayName;const yo=h.forwardRef(({className:t,inset:e,...i},a)=>n.jsx(po,{ref:a,className:P("relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-xs outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",e&&"pl-8",t),...i}));yo.displayName=po.displayName;const ju=h.forwardRef(({className:t,children:e,checked:i,...a},s)=>n.jsxs(fo,{ref:s,className:P("relative flex cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",t),checked:i,...a,children:[n.jsx("span",{className:"absolute left-2 flex h-3.5 w-3.5 items-center justify-center",children:n.jsx(go,{children:n.jsx(cc,{className:"h-4 w-4"})})}),e]}));ju.displayName=fo.displayName;const Fu=h.forwardRef(({className:t,children:e,...i},a)=>n.jsxs(vo,{ref:a,className:P("relative flex cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",t),...i,children:[n.jsx("span",{className:"absolute left-2 flex h-3.5 w-3.5 items-center justify-center",children:n.jsx(go,{children:n.jsx(uc,{className:"h-4 w-4 fill-current"})})}),e]}));Fu.displayName=vo.displayName;const Wu=h.forwardRef(({className:t,inset:e,...i},a)=>n.jsx(mo,{ref:a,className:P("px-2 py-1.5 text-sm font-semibold text-foreground",e&&"pl-8",t),...i}));Wu.displayName=mo.displayName;const Bu=h.forwardRef(({className:t,...e},i)=>n.jsx(Eo,{ref:i,className:P("-mx-1 my-1 h-px bg-border",t),...e}));Bu.displayName=Eo.displayName;function To({children:t,onRename:e}){function i(a){a.stopPropagation(),e==null||e()}return n.jsxs(Pu,{children:[n.jsx(Ou,{children:t}),n.jsx(Ao,{onCloseAutoFocus:a=>{a.preventDefault()},children:n.jsx(Uu,{children:n.jsxs(yo,{onSelect:i,children:[n.jsx(_d,{className:"w-4 h-4 mr-2"}),"Rename"]})})})]})}function Vu(t){const e=pc(t);if(!e)return"OLDER";const a=zn(new Date).getTime(),s=zn(e).getTime(),r=Math.floor((a-s)/(1e3*60*60*24));return r===0?"TODAY":r===1?"YESTERDAY":r<=7?"THIS WEEK":"OLDER"}function Gu(){const t=Ni(),{chatId:e}=ja(),i=e&&e!=="new"?e:null,[a,s]=h.useState([]),[r,o]=h.useState(!0),[l,c]=h.useState(()=>{try{const b=sessionStorage.getItem("chat-listing-open-agents");return b?JSON.parse(b):[]}catch{return[]}}),[p,u]=h.useState("recents"),E=h.useRef(new Map),m=h.useRef(null),v=h.useRef(new Map),g=h.useCallback(b=>{const T=E.current.get(b);T&&T.activateInput()},[]);h.useEffect(()=>{let b=!1;async function T(){o(!0);try{const S=await Es();b||s(S)}catch(S){console.error("Error fetching agents:",S),b||be.error("Failed to load agents",{description:S instanceof Error?S.message:"An error occurred while fetching agents. Please try again.",duration:5e3})}finally{b||o(!1)}}return T(),()=>{b=!0}},[]),h.useEffect(()=>{const T=async S=>{const{conversationId:M,agentName:I}=S.detail;try{const x=await Fa(M);if(!x){console.error("Failed to fetch conversation:",M);return}const L={id:x.name,title:x.title||"Untitled Chat",agent:x.agent||"",timestamp:x.last_activity||x.modified,timestampLabel:x.last_activity||x.modified?Vr(x.last_activity||x.modified):void 0};if(p==="recents")m.current&&m.current(L);else if(p==="agent"&&I){if(v.current.has(I)){const $=v.current.get(I);$&&$(L)}if(!l.includes(I)){const $=[...l,I];c($);try{sessionStorage.setItem("chat-listing-open-agents",JSON.stringify($))}catch(ie){console.error("Failed to save open agents to sessionStorage:",ie)}}}try{const $=await Es();s($)}catch($){console.error("Error refreshing agent counts:",$)}}catch(x){console.error("Error adding conversation to list:",x)}};return window.addEventListener("ivendnext_ai_agents:conversation-created",T),()=>{window.removeEventListener("ivendnext_ai_agents:conversation-created",T)}},[l,p]);const _=h.useCallback(b=>{c(b);try{sessionStorage.setItem("chat-listing-open-agents",JSON.stringify(b))}catch(T){console.error("Failed to save open agents to sessionStorage:",T)}},[]),A=h.useCallback(b=>{t(`/chat/new?agent=${b}`)},[t]);return n.jsxs("div",{className:"h-full min-w-80 bg-sidebar flex flex-col overflow-hidden border-r border-zinc-200",children:[n.jsx("div",{className:"shrink-0 px-3 pt-3 pb-2 sticky top-0 z-1 bg-sidebar",children:n.jsx(qu,{onAgentSelect:A})}),n.jsx("div",{className:"flex-1 min-h-0 overflow-y-auto px-3 pb-3 bg-sidebar [&::-webkit-scrollbar]:w-0 [-ms-overflow-style:none] [scrollbar-width:none]",id:"chat-listing-scroll",children:n.jsxs(Tc,{defaultValue:"recents",value:p,onValueChange:u,className:"space-y-2",children:[n.jsx("div",{className:"sticky top-0 z-1 bg-sidebar",children:n.jsx(xc,{className:"w-full h-8",children:Yu.map(b=>n.jsxs(wc,{className:"w-1/2 space-x-1.5 text-xs font-medium h-7",value:b.value,children:[n.jsx(b.icon,{className:"w-3 h-3"}),n.jsx("span",{children:b.label})]},b.value))})}),n.jsx(Yn,{value:"agent",className:"mt-0",children:r?n.jsx("div",{className:"space-y-4",children:Array.from({length:3}).map((b,T)=>n.jsxs("div",{className:"space-y-2",children:[n.jsxs("div",{className:"flex items-center gap-2",children:[n.jsx(Ie,{className:"h-7 w-7 rounded-full"}),n.jsx(Ie,{className:"h-4 w-40"})]}),n.jsxs("div",{className:"ml-3 pl-3 border-l border-zinc-200 space-y-2",children:[n.jsx(Ie,{className:"h-10 w-full rounded-md"}),n.jsx(Ie,{className:"h-10 w-full rounded-md"})]})]},`agent-skel-${T}`))}):a.length===0?n.jsx("div",{className:"p-3 text-sm text-muted-foreground text-center",children:"No agents with conversations"}):n.jsx(Sc,{type:"multiple",value:l,className:"space-y-2",onValueChange:_,children:a.map(b=>n.jsx(Ku,{agent:b,selectedChatId:i,isOpen:l.includes(b.name),onRename:g,titleRefs:E,onAddItemReady:T=>{v.current.set(b.name,T)}},b.name))})}),n.jsx(Yn,{value:"recents",children:n.jsx(zu,{selectedChatId:i,isActive:p==="recents",onRename:g,titleRefs:E,onAddItemReady:b=>{m.current=b}})})]})})]})}function Ku({agent:t,selectedChatId:e,isOpen:i,onRename:a,titleRefs:s,onAddItemReady:r}){const o=Ni(),l=h.useCallback(g=>{g.stopPropagation(),o(`/chat/new?agent=${t.name}`)},[o,t.name]),{items:c,initialLoading:p,loadingMore:u,hasMore:E,loadMore:m,addItem:v}=Js({fetchFn:async g=>{const _=await hc(t.name,{limit:g.limit||20,start:g.start||0});return{data:_.data.map(A=>({...A,timestampLabel:A.timestamp?Vr(A.timestamp):void 0})),hasMore:_.hasMore}},initialParams:{},pageSize:20,autoLoad:i,autoLoadMore:!1,enabled:i});return h.useEffect(()=>{v&&i&&r&&r(v)},[v,i,r]),n.jsxs(Ic,{value:t.name,className:"border-b-0",children:[n.jsxs(kc,{className:"group gap-2 mb-1 py-1 px-1 hover:bg-zinc-200 cursor-pointer select-none rounded-lg",arrowPosition:"left",children:[n.jsxs("div",{className:"flex-1 flex gap-x-2 items-center",children:[n.jsx(Zt,{variant:"listing_ai",color:t.agent_color||void 0,children:Jt(t.agent_name)}),n.jsx("span",{className:"text-sm font-medium truncate text-zinc-500 group-hover:text-zinc-900 transition-colors",children:t.agent_name})]}),n.jsx("span",{className:"text-[10px] min-w-6 text-zinc-400 bg-zinc-200 px-1.5 py-0.5 rounded-full border border-zinc-200 ml-auto",children:t.conversationCount}),n.jsxs(ke,{size:"icon",variant:"ghost",className:"h-fit w-fit opacity-0 group-hover:opacity-100 p-1 hover:bg-zinc-300 rounded text-zinc-400 hover:text-zinc-900 transition-all ml-1",onClick:l,children:[n.jsx(Xs,{className:"w-3.5 h-3.5"}),n.jsx("span",{className:"sr-only",children:"New Conversation"})]})]}),n.jsx(Mc,{className:"space-y-0.5 ml-3 pl-3 border-l border-zinc-200 overflow-hidden transition-all duration-300 opacity-100",children:p?n.jsxs("div",{className:"space-y-2 p-2",children:[n.jsx(Ie,{className:"h-10 w-full rounded-md"}),n.jsx(Ie,{className:"h-10 w-full rounded-md"})]}):c.length===0&&t.conversationCount===0?n.jsx("div",{className:"p-2 text-xs text-muted-foreground",children:"No conversations"}):c.length===0&&t.conversationCount>0?n.jsxs("div",{className:"space-y-2 p-2",children:[n.jsx(Ie,{className:"h-10 w-full rounded-md"}),n.jsx(Ie,{className:"h-10 w-full rounded-md"})]}):n.jsxs(n.Fragment,{children:[c.map(g=>{const _=e===g.id;return n.jsx(To,{onRename:()=>a(g.id),children:n.jsxs(Zs,{to:`/chat/${g.id}`,onClick:A=>{var S,M;const b=A.target;(b.closest("[data-radix-portal]")||b.closest('[role="menuitem"]')||((M=(S=A.nativeEvent).composedPath)==null?void 0:M.call(S).some(I=>{var x;return((x=I==null?void 0:I.getAttribute)==null?void 0:x.call(I,"role"))==="menuitem"})))&&(A.preventDefault(),A.stopPropagation())},className:P("group flex w-full text-left flex-col p-1 rounded-md cursor-pointer transition-all border-l-2",_?"bg-zinc-200 border-indigo-500":"bg-transparent border-transparent hover:bg-zinc-200 hover:border-zinc-200"),children:[n.jsx(qr,{ref:A=>{A?s.current.set(g.id,A):s.current.delete(g.id)},variant:"agent_list",value:g.title,conversationId:g.id}),n.jsx("p",{className:"ps-1 text-[10px] text-zinc-400 truncate mt-0.5 group-hover:text-zinc-500",children:g.timestampLabel??""})]})},g.id)}),E&&n.jsx("button",{type:"button",onClick:g=>{g.stopPropagation(),m()},disabled:u,className:P("w-full text-xs text-zinc-500 hover:text-zinc-900 py-2 px-2 text-center transition-colors",u&&"opacity-50 cursor-not-allowed"),children:u?"Loading...":"Load More"})]})})]})}function zu({selectedChatId:t,isActive:e,onRename:i,titleRefs:a,onAddItemReady:s}){const r=h.useRef(null),[o,l]=h.useState(new Map),{chats:c,initialLoading:p,loadingMore:u,hasMore:E,error:m,sentinelRef:v,scrollRef:g,addItem:_}=mc({enabled:e,refreshOnRouteChange:!1});h.useEffect(()=>{_&&e&&s&&s(_)},[_,e,s]),h.useEffect(()=>{if(!e||c.length===0)return;const b=Array.from(new Set(c.map(S=>S.agent).filter(Boolean))),T=new Map;Promise.all(b.map(async S=>{try{const M=await Si(S);return{name:S,color:M.agent_color||null}}catch(M){return console.error(`Failed to fetch agent color for ${S}:`,M),{name:S,color:null}}})).then(S=>{S.forEach(({name:M,color:I})=>{T.set(M,I)}),l(T)})},[c,e]),h.useEffect(()=>{var T;const b=(T=r.current)==null?void 0:T.closest("#chat-listing-scroll");b?g.current=b:r.current&&(g.current=r.current)},[g]);const A=h.useMemo(()=>{const b=new Map;for(const S of c){const M=Vu(S.timestamp),I=b.get(M);I?I.push(S):b.set(M,[S])}return["TODAY","YESTERDAY","THIS WEEK","OLDER"].map(S=>[S,b.get(S)??[]])},[c]);return m?n.jsx("div",{className:"p-3 text-sm text-destructive text-center",children:"Failed to load conversations"}):p?n.jsx("div",{className:"space-y-1",children:Array.from({length:6}).map((b,T)=>n.jsxs("div",{className:"flex px-2 py-1.5 gap-2 items-center rounded-md",children:[n.jsx(Ie,{className:"h-6 w-6 rounded-full shrink-0"}),n.jsxs("div",{className:"flex-1 space-y-1.5",children:[n.jsx(Ie,{className:"h-3 w-2/3"}),n.jsx(Ie,{className:"h-2.5 w-1/3"})]})]},`recent-skel-${T}`))}):n.jsx("div",{ref:r,className:"space-y-3",children:A.every(([,b])=>b.length===0)?n.jsx("div",{className:"p-3 text-sm text-muted-foreground text-center",children:"No conversations yet"}):n.jsxs(n.Fragment,{children:[A.map(([b,T])=>T.length===0?null:n.jsxs("div",{children:[n.jsx("span",{className:"px-1 text-[10px] font-medium text-zinc-400 uppercase tracking-wider",children:b}),n.jsx("div",{className:"mt-1 space-y-0.5",children:T.map(S=>{const M=t===S.id;return n.jsx(To,{onRename:()=>i(S.id),children:n.jsxs(Zs,{to:`/chat/${S.id}`,onClick:I=>{var $,ie;const x=I.target;(x.closest("[data-radix-portal]")||x.closest('[role="menuitem"]')||((ie=($=I.nativeEvent).composedPath)==null?void 0:ie.call($).some(R=>{var H;return((H=R==null?void 0:R.getAttribute)==null?void 0:H.call(R,"role"))==="menuitem"})))&&(I.preventDefault(),I.stopPropagation())},className:P("group flex w-full text-left px-2 py-1.5 gap-2 items-center rounded-md cursor-pointer transition-all",M?"bg-zinc-200":"bg-transparent hover:bg-zinc-100"),children:[n.jsx(Zt,{variant:"chat_ai",color:o.get(S.agent)||void 0,children:Jt(S.agent)}),n.jsxs("div",{className:"flex-1 min-w-0 mb-1",children:[n.jsx(qr,{ref:I=>{I?a.current.set(S.id,I):a.current.delete(S.id)},variant:"recents_list",value:S.title,conversationId:S.id}),n.jsx("p",{className:"ps-1 text-xs truncate text-zinc-500",children:S.agent})]}),n.jsx("span",{className:"mb-1 flex-shrink-0 text-[10px] text-zinc-400 flex-shrink-0 self-end",children:S.timestampLabel??""})]})},S.id)})})]},b)),E&&n.jsx("div",{ref:v,className:"h-2 w-full opacity-0","aria-hidden":"true"}),u&&n.jsx("div",{className:"p-2 text-xs text-muted-foreground text-center",children:"Loading more..."})]})})}function qu({onAgentSelect:t}){const[e,i]=h.useState(""),a=h.useCallback(s=>{i(s),t==null||t(s)},[t]);return n.jsxs("div",{className:"flex items-center justify-between",children:[n.jsx("h1",{className:"font-semibold text-sm tracking-tight text-zinc-700",children:"Chat"}),t&&n.jsx(zr,{value:e,onValueChange:a})]})}const Yu=[{value:"agent",label:"By Agent",icon:Ad},{value:"recents",label:"Recents",icon:yd}],tn="#6366F1";function Qu({chatId:t}){const{chatId:e}=ja(),[i]=Fr(),a=t??(e&&e!=="new"?e:null),[s,r]=h.useState(null),[o,l]=h.useState(null);return h.useEffect(()=>{let c=!1;a||l(null);async function p(){try{let u=null,E=null;if(a)try{const m=await Fa(a);m!=null&&m.agent&&(u=m.agent),m!=null&&m.model&&(E=m.model),c||l(E)}catch(m){console.error("Error fetching conversation:",m),c||be.error("Failed to load conversation",{description:"Could not fetch conversation details. Please try again.",duration:5e3});return}else u=i.get("agent");if(u)try{const m=await Si(u);c||r(m)}catch(m){console.error("Error fetching agent:",m),c||(be.error("Failed to load agent",{description:"Could not fetch agent details. Please try again.",duration:5e3}),r(null))}else c||r(null)}catch(u){console.error("Error fetching agent data:",u),c||(be.error("Failed to load agent data",{description:"An unexpected error occurred. Please try again.",duration:5e3}),r(null))}}return p(),()=>{c=!0}},[a,i]),s?n.jsxs("header",{className:"h-16 pl-14 pr-6 border-b border-zinc-200 flex items-center justify-between bg-white/80 backdrop-blur-md sticky top-0 z-10",children:[n.jsxs("div",{className:"flex gap-x-4 items-center",children:[n.jsx(Zt,{variant:"chat_ai",color:s.agent_color||tn,children:Jt(s.agent_name)}),n.jsxs("div",{className:"flex flex-col",children:[n.jsxs("div",{className:"flex gap-x-2 items-center",children:[n.jsx("span",{className:"font-semibold text-sm text-zinc-900",children:s.agent_name}),(o||s.model)&&n.jsx("span",{className:"px-1.5 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 text-[10px] font-medium text-indigo-400",children:o||s.model})]}),s.description&&n.jsx("span",{className:"text-xs text-zinc-500 max-w-[200px] truncate",children:s.description})]})]}),n.jsx("div",{children:n.jsx(Zs,{to:`/agents/${s.name}`,children:n.jsx(ke,{asChild:!0,variant:"outline",className:"gap-x-2 text-xs text-muted-foreground",size:"sm",children:n.jsxs("div",{children:[n.jsx(Td,{className:"w-4 h-4"}),n.jsx("span",{children:"Open Agent"})]})})})})]}):n.jsx("header",{className:"h-16 pl-14 pr-6 border-b border-zinc-200 flex items-center justify-between bg-white/80 backdrop-blur-md sticky top-0 z-10",children:n.jsxs("div",{className:"flex gap-x-4 items-center",children:[n.jsx(Zt,{variant:"chat_ai",children:"?"}),n.jsxs("div",{className:"flex flex-col",children:[n.jsx("span",{className:"font-semibold text-sm text-zinc-900",children:"No agent selected"}),n.jsx("span",{className:"text-xs text-zinc-500",children:"Select an agent to start chatting"})]})]})})}function Xu({conversationId:t,onToolUpdate:e,onNewMessage:i}){h.useEffect(()=>{var o,l,c,p;if(!t)return;const a=(l=(o=window.frappe)==null?void 0:o.boot)==null?void 0:l.sitename,s=window.location.port?(p=(c=window.frappe)==null?void 0:c.boot)==null?void 0:p.socketio_port:"";if(!a){console.warn("Site name not available yet, socket connection will be skipped");return}const r=fc({siteName:a,port:s});return console.log("Socket created for conversation:",t),r.on(`conversation:${t}`,u=>{console.log("Conversation event received:",u),u.type==="new_agent_message"?i==null||i(u):(u.type==="tool_call_started"||u.type==="tool_call_completed"||u.type==="tool_call_failed")&&(e==null||e(u))}),r.on("connect",()=>{console.log("✅ Socket connected for conversation:",t)}),r.on("connect_error",u=>{console.error("❌ Socket connection error:",u)}),r.on("disconnect",u=>{console.warn("⚠️ Socket disconnected:",u)}),()=>{console.log("Cleaning up socket for conversation:",t),r.off(`conversation:${t}`),r.disconnect()}},[t,e,i])}const Zu=Cc,Ju=Lc,eh=Rc,th=({className:t,...e})=>n.jsx(Zu,{className:P("not-prose mb-4 w-full rounded-md border",t),...e}),ih=t=>{const e={"input-streaming":"Pending","input-available":"Running","approval-requested":"Awaiting Approval","approval-responded":"Responded","output-available":"Completed","output-error":"Error","output-denied":"Denied"},i={"input-streaming":n.jsx(Sd,{className:"size-4"}),"input-available":n.jsx(Kn,{className:"size-4 animate-pulse"}),"approval-requested":n.jsx(Kn,{className:"size-4 text-yellow-600"}),"approval-responded":n.jsx(Gn,{className:"size-4 text-blue-600"}),"output-available":n.jsx(Gn,{className:"size-4 text-green-600"}),"output-error":n.jsx(Vn,{className:"size-4 text-red-600"}),"output-denied":n.jsx(Vn,{className:"size-4 text-orange-600"})};return n.jsxs(iu,{className:"gap-1.5 rounded-full text-xs",variant:"secondary",children:[i[t],e[t]]})},ah=({className:t,title:e,type:i,state:a,...s})=>n.jsxs(Ju,{className:P("flex w-full items-center justify-between gap-4 p-3",t),...s,children:[n.jsxs("div",{className:"flex items-center gap-2",children:[n.jsx(xd,{className:"size-4 text-muted-foreground"}),n.jsx("span",{className:"font-medium text-sm",children:e??i.split("-").slice(1).join("-")}),ih(a)]}),n.jsx(wd,{className:"size-4 text-muted-foreground transition-transform group-data-[state=open]:rotate-180"})]}),sh=({className:t,...e})=>n.jsx(eh,{className:P("data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 text-popover-foreground outline-none data-[state=closed]:animate-out data-[state=open]:animate-in",t),...e}),nh=({className:t,input:e,...i})=>n.jsxs("div",{className:P("space-y-2 overflow-hidden p-4",t),...i,children:[n.jsx("h4",{className:"font-medium text-muted-foreground text-xs uppercase tracking-wide",children:"Parameters"}),n.jsx("div",{className:"rounded-md bg-muted/50",children:n.jsx(bs,{code:JSON.stringify(e,null,2),language:"json"})})]}),rh=({className:t,output:e,errorText:i,...a})=>{if(!(e||i))return null;let s=n.jsx("div",{children:e});return typeof e=="object"&&!h.isValidElement(e)?s=n.jsx(bs,{code:JSON.stringify(e,null,2),language:"json"}):typeof e=="string"&&(s=n.jsx(bs,{code:e,language:"json"})),n.jsxs("div",{className:P("space-y-2 p-4",t),...a,children:[n.jsx("h4",{className:"font-medium text-muted-foreground text-xs uppercase tracking-wide",children:i?"Error":"Result"}),n.jsxs("div",{className:P("overflow-x-auto rounded-md text-xs [&_table]:w-full",i?"bg-destructive/10 text-destructive":"bg-muted/50 text-foreground"),children:[i&&n.jsx("div",{children:i}),s]})]})};var oh=Symbol("radix.slottable");function lh(t){const e=({children:i})=>n.jsx(n.Fragment,{children:i});return e.displayName=`${t}.Slottable`,e.__radixId=oh,e}var xo="AlertDialog",[dh]=Or(xo,[Ur]),tt=Ur(),wo=t=>{const{__scopeAlertDialog:e,...i}=t,a=tt(e);return n.jsx(Id,{...a,...i,modal:!0})};wo.displayName=xo;var ch="AlertDialogTrigger",uh=h.forwardRef((t,e)=>{const{__scopeAlertDialog:i,...a}=t,s=tt(i);return n.jsx(Nd,{...s,...a,ref:e})});uh.displayName=ch;var hh="AlertDialogPortal",So=t=>{const{__scopeAlertDialog:e,...i}=t,a=tt(e);return n.jsx(kd,{...a,...i})};So.displayName=hh;var mh="AlertDialogOverlay",Io=h.forwardRef((t,e)=>{const{__scopeAlertDialog:i,...a}=t,s=tt(i);return n.jsx(Dd,{...s,...a,ref:e})});Io.displayName=mh;var Qt="AlertDialogContent",[ph,fh]=dh(Qt),vh=lh("AlertDialogContent"),ko=h.forwardRef((t,e)=>{const{__scopeAlertDialog:i,children:a,...s}=t,r=tt(i),o=h.useRef(null),l=$r(e,o),c=h.useRef(null);return n.jsx(Md,{contentName:Qt,titleName:Mo,docsSlug:"alert-dialog",children:n.jsx(ph,{scope:i,cancelRef:c,children:n.jsxs(Cd,{role:"alertdialog",...r,...s,ref:l,onOpenAutoFocus:Dt(s.onOpenAutoFocus,p=>{var u;p.preventDefault(),(u=c.current)==null||u.focus({preventScroll:!0})}),onPointerDownOutside:p=>p.preventDefault(),onInteractOutside:p=>p.preventDefault(),children:[n.jsx(vh,{children:a}),n.jsx(Eh,{contentRef:o})]})})})});ko.displayName=Qt;var Mo="AlertDialogTitle",Co=h.forwardRef((t,e)=>{const{__scopeAlertDialog:i,...a}=t,s=tt(i);return n.jsx(Ld,{...s,...a,ref:e})});Co.displayName=Mo;var Lo="AlertDialogDescription",Ro=h.forwardRef((t,e)=>{const{__scopeAlertDialog:i,...a}=t,s=tt(i);return n.jsx(Rd,{...s,...a,ref:e})});Ro.displayName=Lo;var gh="AlertDialogAction",Do=h.forwardRef((t,e)=>{const{__scopeAlertDialog:i,...a}=t,s=tt(i);return n.jsx(Hr,{...s,...a,ref:e})});Do.displayName=gh;var No="AlertDialogCancel",Po=h.forwardRef((t,e)=>{const{__scopeAlertDialog:i,...a}=t,{cancelRef:s}=fh(No,i),r=tt(i),o=$r(e,s);return n.jsx(Hr,{...r,...a,ref:o})});Po.displayName=No;var Eh=({contentRef:t})=>{const e=`\`${Qt}\` requires a description for the component to be accessible for screen reader users.

You can add a description to the \`${Qt}\` by passing a \`${Lo}\` component as a child, which also benefits sighted users by adding visible context to the dialog.

Alternatively, you can use your own component as a description by assigning it an \`id\` and passing the same value to the \`aria-describedby\` prop in \`${Qt}\`. If the description is confusing or duplicative for sighted users, you can use the \`@radix-ui/react-visually-hidden\` primitive as a wrapper around your description component.

For more information, see https://radix-ui.com/primitives/docs/components/alert-dialog`;return h.useEffect(()=>{var a;document.getElementById((a=t.current)==null?void 0:a.getAttribute("aria-describedby"))||console.warn(e)},[e,t]),null},bh=wo,_h=So,Oo=Io,Uo=ko,$o=Do,Ho=Po,jo=Co,Fo=Ro;const Ah=bh,yh=_h,Wo=h.forwardRef(({className:t,...e},i)=>n.jsx(Oo,{className:P("fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",t),...e,ref:i}));Wo.displayName=Oo.displayName;const Bo=h.forwardRef(({className:t,...e},i)=>n.jsxs(yh,{children:[n.jsx(Wo,{}),n.jsx(Uo,{ref:i,className:P("fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg",t),...e})]}));Bo.displayName=Uo.displayName;const Vo=({className:t,...e})=>n.jsx("div",{className:P("flex flex-col space-y-2 text-center sm:text-left",t),...e});Vo.displayName="AlertDialogHeader";const Go=({className:t,...e})=>n.jsx("div",{className:P("flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2",t),...e});Go.displayName="AlertDialogFooter";const Ko=h.forwardRef(({className:t,...e},i)=>n.jsx(jo,{ref:i,className:P("text-lg font-semibold",t),...e}));Ko.displayName=jo.displayName;const zo=h.forwardRef(({className:t,...e},i)=>n.jsx(Fo,{ref:i,className:P("text-sm text-muted-foreground",t),...e}));zo.displayName=Fo.displayName;const qo=h.forwardRef(({className:t,...e},i)=>n.jsx($o,{ref:i,className:P(Gr(),t),...e}));qo.displayName=$o.displayName;const Yo=h.forwardRef(({className:t,...e},i)=>n.jsx(Ho,{ref:i,className:P(Gr({variant:"outline"}),"mt-2 sm:mt-0",t),...e}));Yo.displayName=Ho.displayName;function Qo({content:t}){const[e,i]=h.useState(!1);h.useEffect(()=>{if(!e)return;const s=setTimeout(()=>i(!1),4e3);return()=>clearTimeout(s)},[e]);const a=async()=>{if(t)try{if(!(navigator!=null&&navigator.clipboard))throw new Error("Clipboard API not available");await navigator.clipboard.writeText(t),i(!0),be.success("Response copied")}catch(s){console.error(s),be.error("Unable to copy response")}};return n.jsx(ke,{type:"button",variant:"ghost",size:"icon",className:"h-7 w-7",onClick:a,"aria-label":e?"Copied":"Copy response",children:e?n.jsx(Pr,{className:"h-4 w-4"}):n.jsx(Pd,{className:"h-4 w-4"})})}function Th({content:t,agentMessageId:e,onFeedback:i}){const[a,s]=h.useState(!1),[r,o]=h.useState(""),l=()=>{const c=r.trim();i("Thumbs Down",{agentMessageId:e,comments:c||""}),o(""),s(!1)};return n.jsxs(n.Fragment,{children:[n.jsxs("div",{className:"mt-3 flex items-center gap-2 text-muted-foreground",children:[n.jsx(Qo,{content:t}),n.jsx(ke,{type:"button",variant:"ghost",size:"icon",className:"h-7 w-7",onClick:()=>i("Thumbs Up",{agentMessageId:e}),"aria-label":"Mark response helpful",children:n.jsx(Od,{className:"h-4 w-4"})}),n.jsx(ke,{type:"button",variant:"ghost",size:"icon",className:"h-7 w-7",onClick:()=>s(!0),"aria-label":"Mark response not helpful",children:n.jsx(Ud,{className:"h-4 w-4"})})]}),n.jsx(Ah,{open:a,onOpenChange:s,children:n.jsxs(Bo,{children:[n.jsxs(Vo,{children:[n.jsx(Ko,{children:"What went wrong?"}),n.jsx(zo,{children:"Share a brief comment so we can improve this agent's behavior."})]}),n.jsx("div",{className:"space-y-3",children:n.jsx(Kr,{placeholder:"Describe what was incorrect, missing, or unhelpful...",value:r,onChange:c=>o(c.target.value),className:"min-h-[120px]"})}),n.jsxs(Go,{children:[n.jsx(Yo,{onClick:()=>{o("")},children:"Cancel"}),n.jsx(qo,{onClick:l,children:"Submit"})]})]})})]})}const xh=({children:t,as:e="p",className:i,duration:a=2,spread:s=2})=>{const r=h.useMemo(()=>((t==null?void 0:t.length)??0)*s,[t,s]);return n.jsxs(n.Fragment,{children:[n.jsx("style",{children:`
          @keyframes shimmer-slide {
            from { background-position: 100% center; }
            to { background-position: 0% center; }
          }
        `}),n.jsx(e,{className:P("relative inline-block bg-[length:250%_100%,auto] bg-clip-text text-transparent","[--bg:linear-gradient(90deg,#0000_calc(50%-var(--spread)),var(--color-background),#0000_calc(50%+var(--spread)))] [background-repeat:no-repeat,padding-box]",i),style:{"--spread":`${r}px`,backgroundImage:"var(--bg), linear-gradient(var(--color-muted-foreground), var(--color-muted-foreground))",animation:`shimmer-slide ${a}s linear infinite`},children:t})]})},wh=h.memo(xh),Sh=["Listening carefully...","Pretending I have ears...","Speech → text in progress...","Your words are almost ready...","Decoding the spoken word...","Ears wide open...","Catching every word...","Turning sound into words...","Reading between the soundwaves...","Playing it back in my head..."],Zn={default:["Thinking...","Mulling this over...","Connecting the dots...","Crunching thoughts...","On it...","Putting this together...","Working on something good...","Making sense of this..."],"tool-execution":["Getting things done...","Doing the heavy lifting...","Running the numbers...","Working behind the scenes..."],transcribing:Sh},Jn={default:Hd,"tool-execution":$d,transcribing:jr};function Ih({type:t="default",hasTools:e=!1,toolName:i,className:a}){const s=i&&String(i).trim()&&i!=="unknown"?i:null,r=e&&s?`Executing ${s}...`:e?"Executing Tool...":null,o=r?[r]:Zn[t]??Zn.default,[l,c]=h.useState(()=>Math.floor(Math.random()*o.length)),p=o[l%o.length],u=r?Jn["tool-execution"]:Jn[t];return h.useEffect(()=>{if(o.length<=1)return;const E=setInterval(()=>{c(m=>(m+1)%o.length)},3e3);return()=>clearInterval(E)},[o.length]),n.jsxs("div",{className:P("flex items-center gap-2 w-full max-w-md min-h-[60px] py-2",a),children:[n.jsx(u,{className:"size-4 shrink-0 text-muted-foreground"}),n.jsx(wh,{className:"text-sm text-muted-foreground",children:p})]})}const kh=({base64:t,uint8Array:e,mediaType:i,src:a,showDownloadButton:s=!1,onLoad:r,...o})=>{const l=a||(t&&i?`data:${i};base64,${t}`:void 0),c=async()=>{if(l)try{if(l.startsWith("data:")){const g=await(await fetch(l)).blob(),_=window.URL.createObjectURL(g),A=document.createElement("a");A.href=_,A.download="generated-image.png",document.body.appendChild(A),A.click(),document.body.removeChild(A),window.URL.revokeObjectURL(_);return}const u=await(await fetch(l)).blob(),E=window.URL.createObjectURL(u),m=document.createElement("a");m.href=E;try{const g=new URL(l,window.location.origin).pathname.split("/").pop()||"generated-image.png";m.download=g}catch{m.download="generated-image.png"}document.body.appendChild(m),m.click(),document.body.removeChild(m),window.URL.revokeObjectURL(E)}catch(p){console.error("Failed to download image:",p),be.error("Failed to download image")}};return l?n.jsxs("div",{className:"relative group/image-container inline-block",children:[n.jsx("img",{...o,alt:o.alt,className:P("h-auto max-w-full overflow-hidden rounded-md",o.className),src:l,onLoad:r}),s&&n.jsx("div",{className:"absolute top-2 right-2 opacity-0 group-hover/image-container:opacity-100 transition-opacity",children:n.jsxs(ke,{variant:"secondary",size:"icon-sm",className:"bg-white backdrop-blur-sm shadow-md",onClick:c,title:"Download image",children:[n.jsx(jd,{className:"h-4 w-4"}),n.jsx("span",{className:"sr-only",children:"Download image"})]})})]}):null};function Xo(t){switch(t){case"Started":return"input-available";case"Queued":return"input-streaming";case"Completed":return"output-available";case"Failed":return"output-error";default:return"input-streaming"}}function Mh(t){if(typeof document>"u")return t.replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&amp;/g,"&");const e=document.createElement("textarea");return e.innerHTML=t,e.value}function er({content:t,messageKey:e}){const i=Mh(t),a=Vc(i),s=Gc(i),r=Kc(i);if(!a&&!s&&!r)return n.jsx(Qn,{children:t});let o=i,l=[],c=[],p=[];if(r){const u=zc(o);o=u.text,p=u.previews}if(s){const u=qc(o);o=u.text,c=u.previews}if(a){const u=Yc(o);o=u.text,l=u.artifacts}return n.jsxs(n.Fragment,{children:[o&&o.trim()&&n.jsx(Qn,{children:o}),p.map((u,E)=>n.jsx(Qc,{preview:u,messageId:e},`${e}-jsx-${E}`)),c.map((u,E)=>n.jsx(Xc,{preview:u},`${e}-preview-${E}`)),l.map(u=>n.jsx(Zc,{artifact:u,messageId:e},`${e}-${u.id}`))]})}/**
 * @license
 * Copyright 2018 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Modified version of `@lit/react` for vanilla custom elements with support for SSR.
 */const Ch=new Set(["style","children","ref","key","suppressContentEditableWarning","suppressHydrationWarning","dangerouslySetInnerHTML"]),Lh={className:"class",htmlFor:"for"};function Rh(t){return t.toLowerCase()}function tr(t){if(typeof t=="boolean")return t?"":void 0;if(typeof t!="function"&&!(typeof t=="object"&&t!==null))return t}function G({react:t,tagName:e,elementClass:i,events:a,displayName:s,defaultProps:r,toAttributeName:o=Rh,toAttributeValue:l=tr}){const c=Number.parseInt(t.version)>=19,p=t.forwardRef((u,E)=>{var T,S;const m=t.useRef(null),v=t.useRef(new Map),g={},_={},A={},b={};for(const[M,I]of Object.entries(u)){if(Ch.has(M)){A[M]=I;continue}const x=o(Lh[M]??M);if(i.prototype&&M in i.prototype&&!(M in(((T=globalThis.HTMLElement)==null?void 0:T.prototype)??{}))&&!((S=i.observedAttributes)!=null&&S.some($=>$===x))){b[M]=I;continue}if(M.startsWith("on")){g[M]=I;continue}const L=l(I);if(x&&L!=null&&(_[x]=String(L),c||(A[x]=L)),x&&c){const $=tr(I);L!==$?A[x]=L:A[x]=I}}if(typeof window<"u"){for(const M in g){const I=g[M],x=M.endsWith("Capture"),L=((a==null?void 0:a[M])??M.slice(2).toLowerCase()).slice(0,x?-7:void 0);t.useLayoutEffect(()=>{const $=m==null?void 0:m.current;if(!(!$||typeof I!="function"))return $.addEventListener(L,I,x),()=>{$.removeEventListener(L,I,x)}},[m==null?void 0:m.current,I])}t.useLayoutEffect(()=>{if(m.current===null)return;const M=new Map;for(const I in b)ir(m.current,I,b[I]),v.current.delete(I),M.set(I,b[I]);for(const[I,x]of v.current)ir(m.current,I,void 0);v.current=M})}if(typeof window>"u"&&(i!=null&&i.getTemplateHTML)&&(i!=null&&i.shadowRootOptions)){const{mode:M,delegatesFocus:I}=i.shadowRootOptions,x=t.createElement("template",{shadowrootmode:M,shadowrootdelegatesfocus:I,dangerouslySetInnerHTML:{__html:i.getTemplateHTML(_,u)},key:"ce-la-react-ssr-template-shadow-root"});A.children=[x,A.children]}return t.createElement(e,{...r,...A,ref:t.useCallback(M=>{m.current=M,typeof E=="function"?E(M):E!==null&&(E.current=M)},[E])},A.children)});return p.displayName=s??i.name,p}function ir(t,e,i){var a;t[e]=i,i==null&&e in(((a=globalThis.HTMLElement)==null?void 0:a.prototype)??{})&&t.removeAttribute(e)}const w={MEDIA_PLAY_REQUEST:"mediaplayrequest",MEDIA_PAUSE_REQUEST:"mediapauserequest",MEDIA_MUTE_REQUEST:"mediamuterequest",MEDIA_UNMUTE_REQUEST:"mediaunmuterequest",MEDIA_LOOP_REQUEST:"medialooprequest",MEDIA_VOLUME_REQUEST:"mediavolumerequest",MEDIA_SEEK_REQUEST:"mediaseekrequest",MEDIA_AIRPLAY_REQUEST:"mediaairplayrequest",MEDIA_ENTER_FULLSCREEN_REQUEST:"mediaenterfullscreenrequest",MEDIA_EXIT_FULLSCREEN_REQUEST:"mediaexitfullscreenrequest",MEDIA_PREVIEW_REQUEST:"mediapreviewrequest",MEDIA_ENTER_PIP_REQUEST:"mediaenterpiprequest",MEDIA_EXIT_PIP_REQUEST:"mediaexitpiprequest",MEDIA_ENTER_CAST_REQUEST:"mediaentercastrequest",MEDIA_EXIT_CAST_REQUEST:"mediaexitcastrequest",MEDIA_SHOW_TEXT_TRACKS_REQUEST:"mediashowtexttracksrequest",MEDIA_HIDE_TEXT_TRACKS_REQUEST:"mediahidetexttracksrequest",MEDIA_SHOW_SUBTITLES_REQUEST:"mediashowsubtitlesrequest",MEDIA_DISABLE_SUBTITLES_REQUEST:"mediadisablesubtitlesrequest",MEDIA_TOGGLE_SUBTITLES_REQUEST:"mediatogglesubtitlesrequest",MEDIA_PLAYBACK_RATE_REQUEST:"mediaplaybackraterequest",MEDIA_RENDITION_REQUEST:"mediarenditionrequest",MEDIA_AUDIO_TRACK_REQUEST:"mediaaudiotrackrequest",MEDIA_SEEK_TO_LIVE_REQUEST:"mediaseektoliverequest",REGISTER_MEDIA_STATE_RECEIVER:"registermediastatereceiver",UNREGISTER_MEDIA_STATE_RECEIVER:"unregistermediastatereceiver"},z={MEDIA_CHROME_ATTRIBUTES:"mediachromeattributes",MEDIA_CONTROLLER:"mediacontroller"},Zo={MEDIA_AIRPLAY_UNAVAILABLE:"mediaAirplayUnavailable",MEDIA_AUDIO_TRACK_ENABLED:"mediaAudioTrackEnabled",MEDIA_AUDIO_TRACK_LIST:"mediaAudioTrackList",MEDIA_AUDIO_TRACK_UNAVAILABLE:"mediaAudioTrackUnavailable",MEDIA_BUFFERED:"mediaBuffered",MEDIA_CAST_UNAVAILABLE:"mediaCastUnavailable",MEDIA_CHAPTERS_CUES:"mediaChaptersCues",MEDIA_CURRENT_TIME:"mediaCurrentTime",MEDIA_DURATION:"mediaDuration",MEDIA_ENDED:"mediaEnded",MEDIA_ERROR:"mediaError",MEDIA_ERROR_CODE:"mediaErrorCode",MEDIA_ERROR_MESSAGE:"mediaErrorMessage",MEDIA_FULLSCREEN_UNAVAILABLE:"mediaFullscreenUnavailable",MEDIA_HAS_PLAYED:"mediaHasPlayed",MEDIA_HEIGHT:"mediaHeight",MEDIA_IS_AIRPLAYING:"mediaIsAirplaying",MEDIA_IS_CASTING:"mediaIsCasting",MEDIA_IS_FULLSCREEN:"mediaIsFullscreen",MEDIA_IS_PIP:"mediaIsPip",MEDIA_LOADING:"mediaLoading",MEDIA_MUTED:"mediaMuted",MEDIA_LOOP:"mediaLoop",MEDIA_PAUSED:"mediaPaused",MEDIA_PIP_UNAVAILABLE:"mediaPipUnavailable",MEDIA_PLAYBACK_RATE:"mediaPlaybackRate",MEDIA_PREVIEW_CHAPTER:"mediaPreviewChapter",MEDIA_PREVIEW_COORDS:"mediaPreviewCoords",MEDIA_PREVIEW_IMAGE:"mediaPreviewImage",MEDIA_PREVIEW_TIME:"mediaPreviewTime",MEDIA_RENDITION_LIST:"mediaRenditionList",MEDIA_RENDITION_SELECTED:"mediaRenditionSelected",MEDIA_RENDITION_UNAVAILABLE:"mediaRenditionUnavailable",MEDIA_SEEKABLE:"mediaSeekable",MEDIA_STREAM_TYPE:"mediaStreamType",MEDIA_SUBTITLES_LIST:"mediaSubtitlesList",MEDIA_SUBTITLES_SHOWING:"mediaSubtitlesShowing",MEDIA_TARGET_LIVE_WINDOW:"mediaTargetLiveWindow",MEDIA_TIME_IS_LIVE:"mediaTimeIsLive",MEDIA_VOLUME:"mediaVolume",MEDIA_VOLUME_LEVEL:"mediaVolumeLevel",MEDIA_VOLUME_UNAVAILABLE:"mediaVolumeUnavailable",MEDIA_LANG:"mediaLang",MEDIA_WIDTH:"mediaWidth"},Jo=Object.entries(Zo),d=Jo.reduce((t,[e,i])=>(t[e]=i.toLowerCase(),t),{}),Dh={USER_INACTIVE_CHANGE:"userinactivechange",BREAKPOINTS_CHANGE:"breakpointchange",BREAKPOINTS_COMPUTED:"breakpointscomputed"},ei=Jo.reduce((t,[e,i])=>(t[e]=i.toLowerCase(),t),{...Dh});Object.entries(ei).reduce((t,[e,i])=>{const a=d[e];return a&&(t[i]=a),t},{userinactivechange:"userinactive"});const Nh=Object.entries(d).reduce((t,[e,i])=>{const a=ei[e];return a&&(t[i]=a),t},{userinactive:"userinactivechange"}),Qe={SUBTITLES:"subtitles",CAPTIONS:"captions",CHAPTERS:"chapters",METADATA:"metadata"},Xt={DISABLED:"disabled",SHOWING:"showing"},ms={MOUSE:"mouse",PEN:"pen",TOUCH:"touch"},we={UNAVAILABLE:"unavailable",UNSUPPORTED:"unsupported"},et={LIVE:"live",ON_DEMAND:"on-demand",UNKNOWN:"unknown"},Ph={FULLSCREEN:"fullscreen"};function Oh(t){return t==null?void 0:t.map(Uh).join(" ")}function Uh(t){if(t){const{id:e,width:i,height:a}=t;return[e,i,a].filter(s=>s!=null).join(":")}}function $h(t){return t==null?void 0:t.map(Hh).join(" ")}function Hh(t){if(t){const{id:e,kind:i,language:a,label:s}=t;return[e,i,a,s].filter(r=>r!=null).join(":")}}function an(t){return typeof t=="number"&&!Number.isNaN(t)&&Number.isFinite(t)}const el=t=>new Promise(e=>setTimeout(e,t)),jh={"Start airplay":"Start airplay","Stop airplay":"Stop airplay",Audio:"Audio",Captions:"Captions","Enable captions":"Enable captions","Disable captions":"Disable captions","Start casting":"Start casting","Stop casting":"Stop casting","Enter fullscreen mode":"Enter fullscreen mode","Exit fullscreen mode":"Exit fullscreen mode",Mute:"Mute",Unmute:"Unmute",Loop:"Loop","Enter picture in picture mode":"Enter picture in picture mode","Exit picture in picture mode":"Exit picture in picture mode",Play:"Play",Pause:"Pause","Playback rate":"Playback rate","Playback rate {playbackRate}":"Playback rate {playbackRate}",Quality:"Quality","Seek backward":"Seek backward","Seek forward":"Seek forward",Settings:"Settings",Auto:"Auto","audio player":"audio player","video player":"video player",volume:"volume",seek:"seek","closed captions":"closed captions","current playback rate":"current playback rate","playback time":"playback time","media loading":"media loading",settings:"settings","audio tracks":"audio tracks",quality:"quality",play:"play",pause:"pause",mute:"mute",unmute:"unmute","chapter: {chapterName}":"chapter: {chapterName}",live:"live",Off:"Off","start airplay":"start airplay","stop airplay":"stop airplay","start casting":"start casting","stop casting":"stop casting","enter fullscreen mode":"enter fullscreen mode","exit fullscreen mode":"exit fullscreen mode","enter picture in picture mode":"enter picture in picture mode","exit picture in picture mode":"exit picture in picture mode","seek to live":"seek to live","playing live":"playing live","seek back {seekOffset} seconds":"seek back {seekOffset} seconds","seek forward {seekOffset} seconds":"seek forward {seekOffset} seconds","Network Error":"Network Error","Decode Error":"Decode Error","Source Not Supported":"Source Not Supported","Encryption Error":"Encryption Error","A network error caused the media download to fail.":"A network error caused the media download to fail.","A media error caused playback to be aborted. The media could be corrupt or your browser does not support this format.":"A media error caused playback to be aborted. The media could be corrupt or your browser does not support this format.","An unsupported error occurred. The server or network failed, or your browser does not support this format.":"An unsupported error occurred. The server or network failed, or your browser does not support this format.","The media is encrypted and there are no keys to decrypt it.":"The media is encrypted and there are no keys to decrypt it.",hour:"hour",hours:"hours",minute:"minute",minutes:"minutes",second:"second",seconds:"seconds","{time} remaining":"{time} remaining","{currentTime} of {totalTime}":"{currentTime} of {totalTime}","video not loaded, unknown time.":"video not loaded, unknown time."};var ar;const ps={en:jh};let _s=((ar=globalThis.navigator)==null?void 0:ar.language)||"en";const Fh=t=>{_s=t},Wh=t=>{var e,i,a;const[s]=_s.split("-");return((e=ps[_s])==null?void 0:e[t])||((i=ps[s])==null?void 0:i[t])||((a=ps.en)==null?void 0:a[t])||t},k=(t,e={})=>Wh(t).replace(/\{(\w+)\}/g,(i,a)=>a in e?String(e[a]):`{${a}}`),sr=[{singular:"hour",plural:"hours"},{singular:"minute",plural:"minutes"},{singular:"second",plural:"seconds"}],Bh=(t,e)=>{const i=k(t===1?sr[e].singular:sr[e].plural);return`${t} ${i}`},yi=t=>{if(!an(t))return"";const e=Math.abs(t),i=e!==t,a=new Date(0,0,0,0,0,e,0),r=[a.getHours(),a.getMinutes(),a.getSeconds()].map((o,l)=>o&&Bh(o,l)).filter(o=>o).join(", ");return i?k("{time} remaining",{time:r}):r};function mt(t,e){let i=!1;t<0&&(i=!0,t=0-t),t=t<0?0:t;let a=Math.floor(t%60),s=Math.floor(t/60%60),r=Math.floor(t/3600);const o=Math.floor(e/60%60),l=Math.floor(e/3600);return(isNaN(t)||t===1/0)&&(r=s=a="0"),r=r>0||l>0?r+":":"",s=((r||o>=10)&&s<10?"0"+s:s)+":",a=a<10?"0"+a:a,(i?"-":"")+r+s+a}class tl{addEventListener(){}removeEventListener(){}dispatchEvent(){return!0}}class il extends tl{}class nr extends il{constructor(){super(...arguments),this.role=null}}class Vh{observe(){}unobserve(){}disconnect(){}}const al={createElement:function(){return new Ii.HTMLElement},createElementNS:function(){return new Ii.HTMLElement},addEventListener(){},removeEventListener(){},dispatchEvent(t){return!1}},Ii={ResizeObserver:Vh,document:al,Node:il,Element:nr,HTMLElement:class extends nr{constructor(){super(...arguments),this.innerHTML=""}get content(){return new Ii.DocumentFragment}},DocumentFragment:class extends tl{},customElements:{get:function(){},define:function(){},whenDefined:function(){}},localStorage:{getItem(t){return null},setItem(t,e){},removeItem(t){}},CustomEvent:function(){},getComputedStyle:function(){},navigator:{languages:[],get userAgent(){return""}},matchMedia(t){return{matches:!1,media:t}},DOMParser:class{parseFromString(e,i){return{body:{textContent:e}}}}},sl="global"in globalThis&&(globalThis==null?void 0:globalThis.global)===globalThis||typeof window>"u"||typeof window.customElements>"u",nl=Object.keys(Ii).every(t=>t in globalThis),f=sl&&!nl?Ii:globalThis,Ae=sl&&!nl?al:globalThis.document,rr=new WeakMap,sn=t=>{let e=rr.get(t);return e||rr.set(t,e=new Set),e},rl=new f.ResizeObserver(t=>{for(const e of t)for(const i of sn(e.target))i(e)});function ol(t,e){sn(t).add(e),rl.observe(t)}function ll(t,e){const i=sn(t);i.delete(e),i.size||rl.unobserve(t)}function $e(t){const e={};for(const i of t)e[i.name]=i.value;return e}function Gh(t){var e;return(e=Kh(t))!=null?e:Oi(t,"media-controller")}function Kh(t){var e;const{MEDIA_CONTROLLER:i}=z,a=t.getAttribute(i);if(a)return(e=qh(t))==null?void 0:e.getElementById(a)}const dl=(t,e,i=".value")=>{const a=t.querySelector(i);a&&(a.textContent=e)},zh=(t,e)=>{const i=`slot[name="${e}"]`,a=t.shadowRoot.querySelector(i);return a?a.children:[]},cl=(t,e)=>zh(t,e)[0],ai=(t,e)=>!t||!e?!1:t!=null&&t.contains(e)?!0:ai(t,e.getRootNode().host),Oi=(t,e)=>{if(!t)return null;const i=t.closest(e);return i||Oi(t.getRootNode().host,e)};function ul(t=document){var e;const i=t==null?void 0:t.activeElement;return i?(e=ul(i.shadowRoot))!=null?e:i:null}function qh(t){var e;const i=(e=t==null?void 0:t.getRootNode)==null?void 0:e.call(t);return i instanceof ShadowRoot||i instanceof Document?i:null}function hl(t,{depth:e=3,checkOpacity:i=!0,checkVisibilityCSS:a=!0}={}){if(t.checkVisibility)return t.checkVisibility({checkOpacity:i,checkVisibilityCSS:a});let s=t;for(;s&&e>0;){const r=getComputedStyle(s);if(i&&r.opacity==="0"||a&&r.visibility==="hidden"||r.display==="none")return!1;s=s.parentElement,e--}return!0}function Yh(t,e,i,a){const s=a.x-i.x,r=a.y-i.y,o=s*s+r*r;if(o===0)return 0;const l=((t-i.x)*s+(e-i.y)*r)/o;return Math.max(0,Math.min(1,l))}function ue(t,e){const i=Qh(t,a=>a===e);return i||ml(t,e)}function Qh(t,e){var i,a;let s;for(s of(i=t.querySelectorAll("style:not([media])"))!=null?i:[]){let r;try{r=(a=s.sheet)==null?void 0:a.cssRules}catch{continue}for(const o of r??[])if(e(o.selectorText))return o}}function ml(t,e){var i,a;const s=(i=t.querySelectorAll("style:not([media])"))!=null?i:[],r=s==null?void 0:s[s.length-1];if(!(r!=null&&r.sheet))return console.warn("Media Chrome: No style sheet found on style tag of",t),{style:{setProperty:()=>{},removeProperty:()=>"",getPropertyValue:()=>""}};const o=r==null?void 0:r.sheet.insertRule(`${e}{}`,r.sheet.cssRules.length);return(a=r.sheet.cssRules)==null?void 0:a[o]}function J(t,e,i=Number.NaN){const a=t.getAttribute(e);return a!=null?+a:i}function fe(t,e,i){const a=+i;if(i==null||Number.isNaN(a)){t.hasAttribute(e)&&t.removeAttribute(e);return}J(t,e,void 0)!==a&&t.setAttribute(e,`${a}`)}function j(t,e){return t.hasAttribute(e)}function F(t,e,i){if(i==null){t.hasAttribute(e)&&t.removeAttribute(e);return}j(t,e)!=i&&t.toggleAttribute(e,i)}function ee(t,e,i=null){var a;return(a=t.getAttribute(e))!=null?a:i}function te(t,e,i){if(i==null){t.hasAttribute(e)&&t.removeAttribute(e);return}const a=`${i}`;ee(t,e,void 0)!==a&&t.setAttribute(e,a)}var pl=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},De=(t,e,i)=>(pl(t,e,"read from private field"),i?i.call(t):e.get(t)),Xh=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},ji=(t,e,i,a)=>(pl(t,e,"write to private field"),e.set(t,i),i),Ee;function Zh(t){return`
    <style>
      :host {
        display: var(--media-control-display, var(--media-gesture-receiver-display, inline-block));
        box-sizing: border-box;
      }
    </style>
  `}class Wa extends f.HTMLElement{constructor(){if(super(),Xh(this,Ee,void 0),!this.shadowRoot){this.attachShadow(this.constructor.shadowRootOptions);const e=$e(this.attributes);this.shadowRoot.innerHTML=this.constructor.getTemplateHTML(e)}}static get observedAttributes(){return[z.MEDIA_CONTROLLER,d.MEDIA_PAUSED]}attributeChangedCallback(e,i,a){var s,r,o,l,c;e===z.MEDIA_CONTROLLER&&(i&&((r=(s=De(this,Ee))==null?void 0:s.unassociateElement)==null||r.call(s,this),ji(this,Ee,null)),a&&this.isConnected&&(ji(this,Ee,(o=this.getRootNode())==null?void 0:o.getElementById(a)),(c=(l=De(this,Ee))==null?void 0:l.associateElement)==null||c.call(l,this)))}connectedCallback(){var e,i;this.tabIndex=-1,this.setAttribute("aria-hidden","true"),ji(this,Ee,Jh(this)),this.getAttribute(z.MEDIA_CONTROLLER)&&((i=(e=De(this,Ee))==null?void 0:e.associateElement)==null||i.call(e,this)),De(this,Ee)&&(De(this,Ee).addEventListener("pointerdown",this),De(this,Ee).addEventListener("click",this),De(this,Ee).hasAttribute("tabindex")||(De(this,Ee).tabIndex=0))}disconnectedCallback(){var e,i,a,s;this.getAttribute(z.MEDIA_CONTROLLER)&&((i=(e=De(this,Ee))==null?void 0:e.unassociateElement)==null||i.call(e,this)),(a=De(this,Ee))==null||a.removeEventListener("pointerdown",this),(s=De(this,Ee))==null||s.removeEventListener("click",this),ji(this,Ee,null)}handleEvent(e){var i;const a=(i=e.composedPath())==null?void 0:i[0];if(["video","media-controller"].includes(a==null?void 0:a.localName)){if(e.type==="pointerdown")this._pointerType=e.pointerType;else if(e.type==="click"){const{clientX:r,clientY:o}=e,{left:l,top:c,width:p,height:u}=this.getBoundingClientRect(),E=r-l,m=o-c;if(E<0||m<0||E>p||m>u||p===0&&u===0)return;const v=this._pointerType||"mouse";if(this._pointerType=void 0,v===ms.TOUCH){this.handleTap(e);return}else if(v===ms.MOUSE||v===ms.PEN){this.handleMouseClick(e);return}}}}get mediaPaused(){return j(this,d.MEDIA_PAUSED)}set mediaPaused(e){F(this,d.MEDIA_PAUSED,e)}handleTap(e){}handleMouseClick(e){const i=this.mediaPaused?w.MEDIA_PLAY_REQUEST:w.MEDIA_PAUSE_REQUEST;this.dispatchEvent(new f.CustomEvent(i,{composed:!0,bubbles:!0}))}}Ee=new WeakMap;Wa.shadowRootOptions={mode:"open"};Wa.getTemplateHTML=Zh;function Jh(t){var e;const i=t.getAttribute(z.MEDIA_CONTROLLER);return i?(e=t.getRootNode())==null?void 0:e.getElementById(i):Oi(t,"media-controller")}f.customElements.get("media-gesture-receiver")||f.customElements.define("media-gesture-receiver",Wa);var As=Wa,nn=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},oe=(t,e,i)=>(nn(t,e,"read from private field"),i?i.call(t):e.get(t)),_e=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},Fe=(t,e,i,a)=>(nn(t,e,"write to private field"),e.set(t,i),i),Ue=(t,e,i)=>(nn(t,e,"access private method"),i),ci,Sa,Nt,ti,qt,ys,ui,Zi,Ts,fl,xs,vl,ki,Ba,Va,rn,ii,Mi,nt,Ji;const D={AUDIO:"audio",AUTOHIDE:"autohide",BREAKPOINTS:"breakpoints",GESTURES_DISABLED:"gesturesdisabled",KEYBOARD_CONTROL:"keyboardcontrol",NO_AUTOHIDE:"noautohide",USER_INACTIVE:"userinactive",AUTOHIDE_OVER_CONTROLS:"autohideovercontrols"};function em(t){return`
    <style>
      
      :host([${d.MEDIA_IS_FULLSCREEN}]) ::slotted([slot=media]) {
        outline: none;
      }

      :host {
        box-sizing: border-box;
        position: relative;
        display: inline-block;
        line-height: 0;
        background-color: var(--media-background-color, #000);
        overflow: hidden;
      }

      :host(:not([${D.AUDIO}])) [part~=layer]:not([part~=media-layer]) {
        position: absolute;
        top: 0;
        left: 0;
        bottom: 0;
        right: 0;
        display: flex;
        flex-flow: column nowrap;
        align-items: start;
        pointer-events: none;
        background: none;
      }

      slot[name=media] {
        display: var(--media-slot-display, contents);
      }

      
      :host([${D.AUDIO}]) slot[name=media] {
        display: var(--media-slot-display, none);
      }

      
      :host([${D.AUDIO}]) [part~=layer][part~=gesture-layer] {
        height: 0;
        display: block;
      }

      
      :host(:not([${D.AUDIO}])[${D.GESTURES_DISABLED}]) ::slotted([slot=gestures-chrome]),
          :host(:not([${D.AUDIO}])[${D.GESTURES_DISABLED}]) media-gesture-receiver[slot=gestures-chrome] {
        display: none;
      }

      
      ::slotted(:not([slot=media]):not([slot=poster]):not(media-loading-indicator):not([role=dialog]):not([hidden])) {
        pointer-events: auto;
      }

      :host(:not([${D.AUDIO}])) *[part~=layer][part~=centered-layer] {
        align-items: center;
        justify-content: center;
      }

      :host(:not([${D.AUDIO}])) ::slotted(media-gesture-receiver[slot=gestures-chrome]),
      :host(:not([${D.AUDIO}])) media-gesture-receiver[slot=gestures-chrome] {
        align-self: stretch;
        flex-grow: 1;
      }

      slot[name=middle-chrome] {
        display: inline;
        flex-grow: 1;
        pointer-events: none;
        background: none;
      }

      
      ::slotted([slot=media]),
      ::slotted([slot=poster]) {
        width: 100%;
        height: 100%;
      }

      
      :host(:not([${D.AUDIO}])) .spacer {
        flex-grow: 1;
      }

      
      :host(:-webkit-full-screen) {
        
        width: 100% !important;
        height: 100% !important;
      }

      
      ::slotted(:not([slot=media]):not([slot=poster]):not([${D.NO_AUTOHIDE}]):not([hidden]):not([role=dialog])) {
        opacity: 1;
        transition: var(--media-control-transition-in, opacity 0.25s);
      }

      
      :host([${D.USER_INACTIVE}]:not([${d.MEDIA_PAUSED}]):not([${d.MEDIA_IS_AIRPLAYING}]):not([${d.MEDIA_IS_CASTING}]):not([${D.AUDIO}])) ::slotted(:not([slot=media]):not([slot=poster]):not([${D.NO_AUTOHIDE}]):not([role=dialog])) {
        opacity: 0;
        transition: var(--media-control-transition-out, opacity 1s);
      }

      :host([${D.USER_INACTIVE}]:not([${D.NO_AUTOHIDE}]):not([${d.MEDIA_PAUSED}]):not([${d.MEDIA_IS_CASTING}]):not([${D.AUDIO}])) ::slotted([slot=media]) {
        cursor: none;
      }

      :host([${D.USER_INACTIVE}][${D.AUTOHIDE_OVER_CONTROLS}]:not([${D.NO_AUTOHIDE}]):not([${d.MEDIA_PAUSED}]):not([${d.MEDIA_IS_CASTING}]):not([${D.AUDIO}])) * {
        --media-cursor: none;
        cursor: none;
      }


      ::slotted(media-control-bar)  {
        align-self: stretch;
      }

      
      :host(:not([${D.AUDIO}])[${d.MEDIA_HAS_PLAYED}]) slot[name=poster] {
        display: none;
      }

      ::slotted([role=dialog]) {
        width: 100%;
        height: 100%;
        align-self: center;
      }

      ::slotted([role=menu]) {
        align-self: end;
      }
    </style>

    <slot name="media" part="layer media-layer"></slot>
    <slot name="poster" part="layer poster-layer"></slot>
    <slot name="gestures-chrome" part="layer gesture-layer">
      <media-gesture-receiver slot="gestures-chrome">
        <template shadowrootmode="${As.shadowRootOptions.mode}">
          ${As.getTemplateHTML({})}
        </template>
      </media-gesture-receiver>
    </slot>
    <span part="layer vertical-layer">
      <slot name="top-chrome" part="top chrome"></slot>
      <slot name="middle-chrome" part="middle chrome"></slot>
      <slot name="centered-chrome" part="layer centered-layer center centered chrome"></slot>
      
      <slot part="bottom chrome"></slot>
    </span>
    <slot name="dialog" part="layer dialog-layer"></slot>
  `}const tm=Object.values(d),im="sm:384 md:576 lg:768 xl:960";function am(t){gl(t.target,t.contentRect.width)}function gl(t,e){var i;if(!t.isConnected)return;const a=(i=t.getAttribute(D.BREAKPOINTS))!=null?i:im,s=sm(a),r=nm(s,e);let o=!1;if(Object.keys(s).forEach(l=>{if(r.includes(l)){t.hasAttribute(`breakpoint${l}`)||(t.setAttribute(`breakpoint${l}`,""),o=!0);return}t.hasAttribute(`breakpoint${l}`)&&(t.removeAttribute(`breakpoint${l}`),o=!0)}),o){const l=new CustomEvent(ei.BREAKPOINTS_CHANGE,{detail:r});t.dispatchEvent(l)}t.breakpointsComputed||(t.breakpointsComputed=!0,t.dispatchEvent(new CustomEvent(ei.BREAKPOINTS_COMPUTED,{bubbles:!0,composed:!0})))}function sm(t){const e=t.split(/\s+/);return Object.fromEntries(e.map(i=>i.split(":")))}function nm(t,e){return Object.keys(t).filter(i=>e>=parseInt(t[i]))}class Ui extends f.HTMLElement{constructor(){if(super(),_e(this,Ts),_e(this,xs),_e(this,ki),_e(this,Va),_e(this,ii),_e(this,ci,void 0),_e(this,Sa,0),_e(this,Nt,null),_e(this,ti,null),_e(this,qt,void 0),this.breakpointsComputed=!1,_e(this,ys,e=>{const i=this.media;for(const a of e){if(a.type!=="childList")continue;const s=a.removedNodes;for(const r of s){if(r.slot!="media"||a.target!=this)continue;let o=a.previousSibling&&a.previousSibling.previousElementSibling;if(!o||!i)this.mediaUnsetCallback(r);else{let l=o.slot!=="media";for(;(o=o.previousSibling)!==null;)o.slot=="media"&&(l=!1);l&&this.mediaUnsetCallback(r)}}if(i)for(const r of a.addedNodes)r===i&&this.handleMediaUpdated(i)}}),_e(this,ui,!1),_e(this,Zi,e=>{oe(this,ui)||(setTimeout(()=>{am(e),Fe(this,ui,!1)},0),Fe(this,ui,!0))}),_e(this,nt,void 0),_e(this,Ji,()=>{if(!oe(this,nt).assignedElements({flatten:!0}).length){oe(this,Nt)&&this.mediaUnsetCallback(oe(this,Nt));return}this.handleMediaUpdated(this.media)}),!this.shadowRoot){this.attachShadow(this.constructor.shadowRootOptions);const e=$e(this.attributes),i=this.constructor.getTemplateHTML(e);this.shadowRoot.setHTMLUnsafe?this.shadowRoot.setHTMLUnsafe(i):this.shadowRoot.innerHTML=i}Fe(this,ci,new MutationObserver(oe(this,ys)))}static get observedAttributes(){return[D.AUTOHIDE,D.GESTURES_DISABLED].concat(tm).filter(e=>![d.MEDIA_RENDITION_LIST,d.MEDIA_AUDIO_TRACK_LIST,d.MEDIA_CHAPTERS_CUES,d.MEDIA_WIDTH,d.MEDIA_HEIGHT,d.MEDIA_ERROR,d.MEDIA_ERROR_MESSAGE].includes(e))}attributeChangedCallback(e,i,a){e.toLowerCase()==D.AUTOHIDE&&(this.autohide=a)}get media(){let e=this.querySelector(":scope > [slot=media]");return(e==null?void 0:e.nodeName)=="SLOT"&&(e=e.assignedElements({flatten:!0})[0]),e}async handleMediaUpdated(e){e&&(Fe(this,Nt,e),e.localName.includes("-")&&await f.customElements.whenDefined(e.localName),this.mediaSetCallback(e))}connectedCallback(){var e;oe(this,ci).observe(this,{childList:!0,subtree:!0}),ol(this,oe(this,Zi));const i=this.getAttribute(D.AUDIO)!=null,a=k(i?"audio player":"video player");this.setAttribute("role","region"),this.setAttribute("aria-label",a),this.handleMediaUpdated(this.media),this.setAttribute(D.USER_INACTIVE,""),gl(this,this.getBoundingClientRect().width);const s=this.querySelector(":scope > slot[slot=media]");s&&(Fe(this,nt,s),oe(this,nt).addEventListener("slotchange",oe(this,Ji))),this.addEventListener("pointerdown",this),this.addEventListener("pointermove",this),this.addEventListener("pointerup",this),this.addEventListener("mouseleave",this),this.addEventListener("keyup",this),(e=f.window)==null||e.addEventListener("mouseup",this)}disconnectedCallback(){var e;ll(this,oe(this,Zi)),clearTimeout(oe(this,ti)),oe(this,ci).disconnect(),this.media&&this.mediaUnsetCallback(this.media),(e=f.window)==null||e.removeEventListener("mouseup",this),this.removeEventListener("pointerdown",this),this.removeEventListener("pointermove",this),this.removeEventListener("pointerup",this),this.removeEventListener("mouseleave",this),this.removeEventListener("keyup",this),oe(this,nt)&&(oe(this,nt).removeEventListener("slotchange",oe(this,Ji)),Fe(this,nt,null))}mediaSetCallback(e){}mediaUnsetCallback(e){Fe(this,Nt,null)}handleEvent(e){switch(e.type){case"pointerdown":Fe(this,Sa,e.timeStamp);break;case"pointermove":Ue(this,Ts,fl).call(this,e);break;case"pointerup":Ue(this,xs,vl).call(this,e);break;case"mouseleave":Ue(this,ki,Ba).call(this);break;case"mouseup":this.removeAttribute(D.KEYBOARD_CONTROL);break;case"keyup":Ue(this,ii,Mi).call(this),this.setAttribute(D.KEYBOARD_CONTROL,"");break}}set autohide(e){const i=Number(e);Fe(this,qt,isNaN(i)?0:i)}get autohide(){return(oe(this,qt)===void 0?2:oe(this,qt)).toString()}get breakpoints(){return ee(this,D.BREAKPOINTS)}set breakpoints(e){te(this,D.BREAKPOINTS,e)}get audio(){return j(this,D.AUDIO)}set audio(e){F(this,D.AUDIO,e)}get gesturesDisabled(){return j(this,D.GESTURES_DISABLED)}set gesturesDisabled(e){F(this,D.GESTURES_DISABLED,e)}get keyboardControl(){return j(this,D.KEYBOARD_CONTROL)}set keyboardControl(e){F(this,D.KEYBOARD_CONTROL,e)}get noAutohide(){return j(this,D.NO_AUTOHIDE)}set noAutohide(e){F(this,D.NO_AUTOHIDE,e)}get autohideOverControls(){return j(this,D.AUTOHIDE_OVER_CONTROLS)}set autohideOverControls(e){F(this,D.AUTOHIDE_OVER_CONTROLS,e)}get userInteractive(){return j(this,D.USER_INACTIVE)}set userInteractive(e){F(this,D.USER_INACTIVE,e)}}ci=new WeakMap;Sa=new WeakMap;Nt=new WeakMap;ti=new WeakMap;qt=new WeakMap;ys=new WeakMap;ui=new WeakMap;Zi=new WeakMap;Ts=new WeakSet;fl=function(t){if(t.pointerType!=="mouse"&&t.timeStamp-oe(this,Sa)<250)return;Ue(this,Va,rn).call(this),clearTimeout(oe(this,ti));const e=this.hasAttribute(D.AUTOHIDE_OVER_CONTROLS);([this,this.media].includes(t.target)||e)&&Ue(this,ii,Mi).call(this)};xs=new WeakSet;vl=function(t){if(t.pointerType==="touch"){const e=!this.hasAttribute(D.USER_INACTIVE);[this,this.media].includes(t.target)&&e?Ue(this,ki,Ba).call(this):Ue(this,ii,Mi).call(this)}else t.composedPath().some(e=>["media-play-button","media-fullscreen-button"].includes(e==null?void 0:e.localName))&&Ue(this,ii,Mi).call(this)};ki=new WeakSet;Ba=function(){if(oe(this,qt)<0||this.hasAttribute(D.USER_INACTIVE))return;this.setAttribute(D.USER_INACTIVE,"");const t=new f.CustomEvent(ei.USER_INACTIVE_CHANGE,{composed:!0,bubbles:!0,detail:!0});this.dispatchEvent(t)};Va=new WeakSet;rn=function(){if(!this.hasAttribute(D.USER_INACTIVE))return;this.removeAttribute(D.USER_INACTIVE);const t=new f.CustomEvent(ei.USER_INACTIVE_CHANGE,{composed:!0,bubbles:!0,detail:!1});this.dispatchEvent(t)};ii=new WeakSet;Mi=function(){Ue(this,Va,rn).call(this),clearTimeout(oe(this,ti));const t=parseInt(this.autohide);t<0||Fe(this,ti,setTimeout(()=>{Ue(this,ki,Ba).call(this)},t*1e3))};nt=new WeakMap;Ji=new WeakMap;Ui.shadowRootOptions={mode:"open"};Ui.getTemplateHTML=em;f.customElements.get("media-container")||f.customElements.define("media-container",Ui);var rm=Ui,El=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},pe=(t,e,i)=>(El(t,e,"read from private field"),i?i.call(t):e.get(t)),ni=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},Fi=(t,e,i,a)=>(El(t,e,"write to private field"),e.set(t,i),i),Pt,Ot,Ia,_t,Je,rt;class bl{constructor(e,i,{defaultValue:a}={defaultValue:void 0}){ni(this,Je),ni(this,Pt,void 0),ni(this,Ot,void 0),ni(this,Ia,void 0),ni(this,_t,new Set),Fi(this,Pt,e),Fi(this,Ot,i),Fi(this,Ia,new Set(a))}[Symbol.iterator](){return pe(this,Je,rt).values()}get length(){return pe(this,Je,rt).size}get value(){var e;return(e=[...pe(this,Je,rt)].join(" "))!=null?e:""}set value(e){var i;e!==this.value&&(Fi(this,_t,new Set),this.add(...(i=e==null?void 0:e.split(" "))!=null?i:[]))}toString(){return this.value}item(e){return[...pe(this,Je,rt)][e]}values(){return pe(this,Je,rt).values()}forEach(e,i){pe(this,Je,rt).forEach(e,i)}add(...e){var i,a;e.forEach(s=>pe(this,_t).add(s)),!(this.value===""&&!((i=pe(this,Pt))!=null&&i.hasAttribute(`${pe(this,Ot)}`)))&&((a=pe(this,Pt))==null||a.setAttribute(`${pe(this,Ot)}`,`${this.value}`))}remove(...e){var i;e.forEach(a=>pe(this,_t).delete(a)),(i=pe(this,Pt))==null||i.setAttribute(`${pe(this,Ot)}`,`${this.value}`)}contains(e){return pe(this,Je,rt).has(e)}toggle(e,i){return typeof i<"u"?i?(this.add(e),!0):(this.remove(e),!1):this.contains(e)?(this.remove(e),!1):(this.add(e),!0)}replace(e,i){return this.remove(e),this.add(i),e===i}}Pt=new WeakMap;Ot=new WeakMap;Ia=new WeakMap;_t=new WeakMap;Je=new WeakSet;rt=function(){return pe(this,_t).size?pe(this,_t):pe(this,Ia)};const om=(t="")=>t.split(/\s+/),_l=(t="")=>{const[e,i,a]=t.split(":"),s=a?decodeURIComponent(a):void 0;return{kind:e==="cc"?Qe.CAPTIONS:Qe.SUBTITLES,language:i,label:s}},Al=(t="",e={})=>om(t).map(i=>{const a=_l(i);return{...e,...a}}),yl=t=>t?Array.isArray(t)?t.map(e=>typeof e=="string"?_l(e):e):typeof t=="string"?Al(t):[t]:[],lm=({kind:t,label:e,language:i}={kind:"subtitles"})=>e?`${t==="captions"?"cc":"sb"}:${i}:${encodeURIComponent(e)}`:i,ws=(t=[])=>Array.prototype.map.call(t,lm).join(" "),dm=(t,e)=>i=>i[t]===e,Tl=t=>{const e=Object.entries(t).map(([i,a])=>dm(i,a));return i=>e.every(a=>a(i))},Ti=(t,e=[],i=[])=>{const a=yl(i).map(Tl),s=r=>a.some(o=>o(r));Array.from(e).filter(s).forEach(r=>{r.mode=t})},Ga=(t,e=()=>!0)=>{if(!(t!=null&&t.textTracks))return[];const i=typeof e=="function"?e:Tl(e);return Array.from(t.textTracks).filter(i)},cm=t=>{var e;return!!((e=t.mediaSubtitlesShowing)!=null&&e.length)||t.hasAttribute(d.MEDIA_SUBTITLES_SHOWING)},um=t=>{var e;const{media:i,fullscreenElement:a}=t;try{const s=a&&"requestFullscreen"in a?"requestFullscreen":a&&"webkitRequestFullScreen"in a?"webkitRequestFullScreen":void 0;if(s){const r=(e=a[s])==null?void 0:e.call(a);if(r instanceof Promise)return r.catch(()=>{})}else i!=null&&i.webkitEnterFullscreen?i.webkitEnterFullscreen():i!=null&&i.requestFullscreen&&i.requestFullscreen()}catch(s){console.error(s)}},or="exitFullscreen"in Ae?"exitFullscreen":"webkitExitFullscreen"in Ae?"webkitExitFullscreen":"webkitCancelFullScreen"in Ae?"webkitCancelFullScreen":void 0,hm=t=>{var e;const{documentElement:i}=t;if(or){const a=(e=i==null?void 0:i[or])==null?void 0:e.call(i);if(a instanceof Promise)return a.catch(()=>{})}},hi="fullscreenElement"in Ae?"fullscreenElement":"webkitFullscreenElement"in Ae?"webkitFullscreenElement":void 0,mm=t=>{const{documentElement:e,media:i}=t,a=e==null?void 0:e[hi];return!a&&"webkitDisplayingFullscreen"in i&&"webkitPresentationMode"in i&&i.webkitDisplayingFullscreen&&i.webkitPresentationMode===Ph.FULLSCREEN?i:a},pm=t=>{var e;const{media:i,documentElement:a,fullscreenElement:s=i}=t;if(!i||!a)return!1;const r=mm(t);if(!r)return!1;if(r===s||r===i)return!0;if(r.localName.includes("-")){let o=r.shadowRoot;if(!(hi in o))return ai(r,s);for(;o!=null&&o[hi];){if(o[hi]===s)return!0;o=(e=o[hi])==null?void 0:e.shadowRoot}}return!1},fm="fullscreenEnabled"in Ae?"fullscreenEnabled":"webkitFullscreenEnabled"in Ae?"webkitFullscreenEnabled":void 0,vm=t=>{const{documentElement:e,media:i}=t;return!!(e!=null&&e[fm])||i&&"webkitSupportsFullscreen"in i};let Wi;const on=()=>{var t,e;return Wi||(Wi=(e=(t=Ae)==null?void 0:t.createElement)==null?void 0:e.call(t,"video"),Wi)},gm=async(t=on())=>{if(!t)return!1;const e=t.volume;t.volume=e/2+.1;const i=new AbortController,a=await Promise.race([Em(t,i.signal),bm(t,e)]);return i.abort(),a},Em=(t,e)=>new Promise(i=>{t.addEventListener("volumechange",()=>i(!0),{signal:e})}),bm=async(t,e)=>{for(let i=0;i<10;i++){if(t.volume===e)return!1;await el(10)}return t.volume!==e},_m=/.*Version\/.*Safari\/.*/.test(f.navigator.userAgent),xl=(t=on())=>f.matchMedia("(display-mode: standalone)").matches&&_m?!1:typeof(t==null?void 0:t.requestPictureInPicture)=="function",wl=(t=on())=>vm({documentElement:Ae,media:t}),Am=wl(),ym=xl(),Tm=!!f.WebKitPlaybackTargetAvailabilityEvent,xm=!!f.chrome,ka=t=>Ga(t.media,e=>[Qe.SUBTITLES,Qe.CAPTIONS].includes(e.kind)).sort((e,i)=>e.kind>=i.kind?1:-1),Sl=t=>Ga(t.media,e=>e.mode===Xt.SHOWING&&[Qe.SUBTITLES,Qe.CAPTIONS].includes(e.kind)),Il=(t,e)=>{const i=ka(t),a=Sl(t),s=!!a.length;if(i.length){if(e===!1||s&&e!==!0)Ti(Xt.DISABLED,i,a);else if(e===!0||!s&&e!==!1){let r=i[0];const{options:o}=t;if(!(o!=null&&o.noSubtitlesLangPref)){const u=f.localStorage.getItem("media-chrome-pref-subtitles-lang"),E=u?[u,...f.navigator.languages]:f.navigator.languages,m=i.filter(v=>E.some(g=>v.language.toLowerCase().startsWith(g.split("-")[0]))).sort((v,g)=>{const _=E.findIndex(b=>v.language.toLowerCase().startsWith(b.split("-")[0])),A=E.findIndex(b=>g.language.toLowerCase().startsWith(b.split("-")[0]));return _-A});m[0]&&(r=m[0])}const{language:l,label:c,kind:p}=r;Ti(Xt.DISABLED,i,a),Ti(Xt.SHOWING,i,[{language:l,label:c,kind:p}])}}},ln=(t,e)=>t===e?!0:t==null||e==null||typeof t!=typeof e?!1:typeof t=="number"&&Number.isNaN(t)&&Number.isNaN(e)?!0:typeof t!="object"?!1:Array.isArray(t)?wm(t,e):Object.entries(t).every(([i,a])=>i in e&&ln(a,e[i])),wm=(t,e)=>{const i=Array.isArray(t),a=Array.isArray(e);return i!==a?!1:i||a?t.length!==e.length?!1:t.every((s,r)=>ln(s,e[r])):!0},Sm=Object.values(et);let Ma;const Im=gm().then(t=>(Ma=t,Ma)),km=async(...t)=>{await Promise.all(t.filter(e=>e).map(async e=>{if(!("localName"in e&&e instanceof f.HTMLElement))return;const i=e.localName;if(!i.includes("-"))return;const a=f.customElements.get(i);a&&e instanceof a||(await f.customElements.whenDefined(i),f.customElements.upgrade(e))}))},Mm=new f.DOMParser,Cm=t=>t&&(Mm.parseFromString(t,"text/html").body.textContent||t),mi={mediaError:{get(t,e){const{media:i}=t;if((e==null?void 0:e.type)!=="playing")return i==null?void 0:i.error},mediaEvents:["emptied","error","playing"]},mediaErrorCode:{get(t,e){var i;const{media:a}=t;if((e==null?void 0:e.type)!=="playing")return(i=a==null?void 0:a.error)==null?void 0:i.code},mediaEvents:["emptied","error","playing"]},mediaErrorMessage:{get(t,e){var i,a;const{media:s}=t;if((e==null?void 0:e.type)!=="playing")return(a=(i=s==null?void 0:s.error)==null?void 0:i.message)!=null?a:""},mediaEvents:["emptied","error","playing"]},mediaWidth:{get(t){var e;const{media:i}=t;return(e=i==null?void 0:i.videoWidth)!=null?e:0},mediaEvents:["resize"]},mediaHeight:{get(t){var e;const{media:i}=t;return(e=i==null?void 0:i.videoHeight)!=null?e:0},mediaEvents:["resize"]},mediaPaused:{get(t){var e;const{media:i}=t;return(e=i==null?void 0:i.paused)!=null?e:!0},set(t,e){var i;const{media:a}=e;a&&(t?a.pause():(i=a.play())==null||i.catch(()=>{}))},mediaEvents:["play","playing","pause","emptied"]},mediaHasPlayed:{get(t,e){const{media:i}=t;return i?e?e.type==="playing":!i.paused:!1},mediaEvents:["playing","emptied"]},mediaEnded:{get(t){var e;const{media:i}=t;return(e=i==null?void 0:i.ended)!=null?e:!1},mediaEvents:["seeked","ended","emptied"]},mediaPlaybackRate:{get(t){var e;const{media:i}=t;return(e=i==null?void 0:i.playbackRate)!=null?e:1},set(t,e){const{media:i}=e;i&&Number.isFinite(+t)&&(i.playbackRate=+t)},mediaEvents:["ratechange","loadstart"]},mediaMuted:{get(t){var e;const{media:i}=t;return(e=i==null?void 0:i.muted)!=null?e:!1},set(t,e){const{media:i,options:{noMutedPref:a}={}}=e;if(i){i.muted=t;try{const s=f.localStorage.getItem("media-chrome-pref-muted")!==null,r=i.hasAttribute("muted");if(a){s&&f.localStorage.removeItem("media-chrome-pref-muted");return}if(r&&!s)return;f.localStorage.setItem("media-chrome-pref-muted",t?"true":"false")}catch(s){console.debug("Error setting muted pref",s)}}},mediaEvents:["volumechange"],stateOwnersUpdateHandlers:[(t,e)=>{const{options:{noMutedPref:i}}=e,{media:a}=e;if(!(!a||a.muted||i))try{const s=f.localStorage.getItem("media-chrome-pref-muted")==="true";mi.mediaMuted.set(s,e),t(s)}catch(s){console.debug("Error getting muted pref",s)}}]},mediaLoop:{get(t){const{media:e}=t;return e==null?void 0:e.loop},set(t,e){const{media:i}=e;i&&(i.loop=t)},mediaEvents:["medialooprequest"]},mediaVolume:{get(t){var e;const{media:i}=t;return(e=i==null?void 0:i.volume)!=null?e:1},set(t,e){const{media:i,options:{noVolumePref:a}={}}=e;if(i){try{t==null?f.localStorage.removeItem("media-chrome-pref-volume"):!i.hasAttribute("muted")&&!a&&f.localStorage.setItem("media-chrome-pref-volume",t.toString())}catch(s){console.debug("Error setting volume pref",s)}Number.isFinite(+t)&&(i.volume=+t)}},mediaEvents:["volumechange"],stateOwnersUpdateHandlers:[(t,e)=>{const{options:{noVolumePref:i}}=e;if(!i)try{const{media:a}=e;if(!a)return;const s=f.localStorage.getItem("media-chrome-pref-volume");if(s==null)return;mi.mediaVolume.set(+s,e),t(+s)}catch(a){console.debug("Error getting volume pref",a)}}]},mediaVolumeLevel:{get(t){const{media:e}=t;return typeof(e==null?void 0:e.volume)>"u"?"high":e.muted||e.volume===0?"off":e.volume<.5?"low":e.volume<.75?"medium":"high"},mediaEvents:["volumechange"]},mediaCurrentTime:{get(t){var e;const{media:i}=t;return(e=i==null?void 0:i.currentTime)!=null?e:0},set(t,e){const{media:i}=e;!i||!an(t)||(i.currentTime=t)},mediaEvents:["timeupdate","loadedmetadata"]},mediaDuration:{get(t){const{media:e,options:{defaultDuration:i}={}}=t;return i&&(!e||!e.duration||Number.isNaN(e.duration)||!Number.isFinite(e.duration))?i:Number.isFinite(e==null?void 0:e.duration)?e.duration:Number.NaN},mediaEvents:["durationchange","loadedmetadata","emptied"]},mediaLoading:{get(t){const{media:e}=t;return(e==null?void 0:e.readyState)<3},mediaEvents:["waiting","playing","emptied"]},mediaSeekable:{get(t){var e;const{media:i}=t;if(!((e=i==null?void 0:i.seekable)!=null&&e.length))return;const a=i.seekable.start(0),s=i.seekable.end(i.seekable.length-1);if(!(!a&&!s))return[Number(a.toFixed(3)),Number(s.toFixed(3))]},mediaEvents:["loadedmetadata","emptied","progress","seekablechange"]},mediaBuffered:{get(t){var e;const{media:i}=t,a=(e=i==null?void 0:i.buffered)!=null?e:[];return Array.from(a).map((s,r)=>[Number(a.start(r).toFixed(3)),Number(a.end(r).toFixed(3))])},mediaEvents:["progress","emptied"]},mediaStreamType:{get(t){const{media:e,options:{defaultStreamType:i}={}}=t,a=[et.LIVE,et.ON_DEMAND].includes(i)?i:void 0;if(!e)return a;const{streamType:s}=e;if(Sm.includes(s))return s===et.UNKNOWN?a:s;const r=e.duration;return r===1/0?et.LIVE:Number.isFinite(r)?et.ON_DEMAND:a},mediaEvents:["emptied","durationchange","loadedmetadata","streamtypechange"]},mediaTargetLiveWindow:{get(t){const{media:e}=t;if(!e)return Number.NaN;const{targetLiveWindow:i}=e,a=mi.mediaStreamType.get(t);return(i==null||Number.isNaN(i))&&a===et.LIVE?0:i},mediaEvents:["emptied","durationchange","loadedmetadata","streamtypechange","targetlivewindowchange"]},mediaTimeIsLive:{get(t){const{media:e,options:{liveEdgeOffset:i=10}={}}=t;if(!e)return!1;if(typeof e.liveEdgeStart=="number")return Number.isNaN(e.liveEdgeStart)?!1:e.currentTime>=e.liveEdgeStart;if(!(mi.mediaStreamType.get(t)===et.LIVE))return!1;const s=e.seekable;if(!s)return!0;if(!s.length)return!1;const r=s.end(s.length-1)-i;return e.currentTime>=r},mediaEvents:["playing","timeupdate","progress","waiting","emptied"]},mediaSubtitlesList:{get(t){return ka(t).map(({kind:e,label:i,language:a})=>({kind:e,label:i,language:a}))},mediaEvents:["loadstart"],textTracksEvents:["addtrack","removetrack"]},mediaSubtitlesShowing:{get(t){return Sl(t).map(({kind:e,label:i,language:a})=>({kind:e,label:i,language:a}))},mediaEvents:["loadstart"],textTracksEvents:["addtrack","removetrack","change"],stateOwnersUpdateHandlers:[(t,e)=>{var i,a;const{media:s,options:r}=e;if(!s)return;const o=l=>{var c;!r.defaultSubtitles||l&&![Qe.CAPTIONS,Qe.SUBTITLES].includes((c=l==null?void 0:l.track)==null?void 0:c.kind)||Il(e,!0)};return s.addEventListener("loadstart",o),(i=s.textTracks)==null||i.addEventListener("addtrack",o),(a=s.textTracks)==null||a.addEventListener("removetrack",o),()=>{var l,c;s.removeEventListener("loadstart",o),(l=s.textTracks)==null||l.removeEventListener("addtrack",o),(c=s.textTracks)==null||c.removeEventListener("removetrack",o)}}]},mediaChaptersCues:{get(t){var e;const{media:i}=t;if(!i)return[];const[a]=Ga(i,{kind:Qe.CHAPTERS});return Array.from((e=a==null?void 0:a.cues)!=null?e:[]).map(({text:s,startTime:r,endTime:o})=>({text:Cm(s),startTime:r,endTime:o}))},mediaEvents:["loadstart","loadedmetadata"],textTracksEvents:["addtrack","removetrack","change"],stateOwnersUpdateHandlers:[(t,e)=>{var i;const{media:a}=e;if(!a)return;const s=a.querySelector('track[kind="chapters"][default][src]'),r=(i=a.shadowRoot)==null?void 0:i.querySelector(':is(video,audio) > track[kind="chapters"][default][src]');return s==null||s.addEventListener("load",t),r==null||r.addEventListener("load",t),()=>{s==null||s.removeEventListener("load",t),r==null||r.removeEventListener("load",t)}}]},mediaIsPip:{get(t){var e,i;const{media:a,documentElement:s}=t;if(!a||!s||!s.pictureInPictureElement)return!1;if(s.pictureInPictureElement===a)return!0;if(s.pictureInPictureElement instanceof HTMLMediaElement)return(e=a.localName)!=null&&e.includes("-")?ai(a,s.pictureInPictureElement):!1;if(s.pictureInPictureElement.localName.includes("-")){let r=s.pictureInPictureElement.shadowRoot;for(;r!=null&&r.pictureInPictureElement;){if(r.pictureInPictureElement===a)return!0;r=(i=r.pictureInPictureElement)==null?void 0:i.shadowRoot}}return!1},set(t,e){const{media:i}=e;if(i)if(t){if(!Ae.pictureInPictureEnabled){console.warn("MediaChrome: Picture-in-picture is not enabled");return}if(!i.requestPictureInPicture){console.warn("MediaChrome: The current media does not support picture-in-picture");return}const a=()=>{console.warn("MediaChrome: The media is not ready for picture-in-picture. It must have a readyState > 0.")};i.requestPictureInPicture().catch(s=>{if(s.code===11){if(!i.src){console.warn("MediaChrome: The media is not ready for picture-in-picture. It must have a src set.");return}if(i.readyState===0&&i.preload==="none"){const r=()=>{i.removeEventListener("loadedmetadata",o),i.preload="none"},o=()=>{i.requestPictureInPicture().catch(a),r()};i.addEventListener("loadedmetadata",o),i.preload="metadata",setTimeout(()=>{i.readyState===0&&a(),r()},1e3)}else throw s}else throw s})}else Ae.pictureInPictureElement&&Ae.exitPictureInPicture()},mediaEvents:["enterpictureinpicture","leavepictureinpicture"]},mediaRenditionList:{get(t){var e;const{media:i}=t;return[...(e=i==null?void 0:i.videoRenditions)!=null?e:[]].map(a=>({...a}))},mediaEvents:["emptied","loadstart"],videoRenditionsEvents:["addrendition","removerendition"]},mediaRenditionSelected:{get(t){var e,i,a;const{media:s}=t;return(a=(i=s==null?void 0:s.videoRenditions)==null?void 0:i[(e=s.videoRenditions)==null?void 0:e.selectedIndex])==null?void 0:a.id},set(t,e){const{media:i}=e;if(!(i!=null&&i.videoRenditions)){console.warn("MediaController: Rendition selection not supported by this media.");return}const a=t,s=Array.prototype.findIndex.call(i.videoRenditions,r=>r.id==a);i.videoRenditions.selectedIndex!=s&&(i.videoRenditions.selectedIndex=s)},mediaEvents:["emptied"],videoRenditionsEvents:["addrendition","removerendition","change"]},mediaAudioTrackList:{get(t){var e;const{media:i}=t;return[...(e=i==null?void 0:i.audioTracks)!=null?e:[]]},mediaEvents:["emptied","loadstart"],audioTracksEvents:["addtrack","removetrack"]},mediaAudioTrackEnabled:{get(t){var e,i;const{media:a}=t;return(i=[...(e=a==null?void 0:a.audioTracks)!=null?e:[]].find(s=>s.enabled))==null?void 0:i.id},set(t,e){const{media:i}=e;if(!(i!=null&&i.audioTracks)){console.warn("MediaChrome: Audio track selection not supported by this media.");return}const a=t;for(const s of i.audioTracks)s.enabled=a==s.id},mediaEvents:["emptied"],audioTracksEvents:["addtrack","removetrack","change"]},mediaIsFullscreen:{get(t){return pm(t)},set(t,e,i){var a,s;t?(um(e),i.detail&&!((a=e.media)!=null&&a.inert)&&((s=e.media)==null||s.focus())):hm(e)},rootEvents:["fullscreenchange","webkitfullscreenchange"],mediaEvents:["webkitbeginfullscreen","webkitendfullscreen","webkitpresentationmodechanged"]},mediaIsCasting:{get(t){var e;const{media:i}=t;return!(i!=null&&i.remote)||((e=i.remote)==null?void 0:e.state)==="disconnected"?!1:!!i.remote.state},set(t,e){var i,a;const{media:s}=e;if(s&&!(t&&((i=s.remote)==null?void 0:i.state)!=="disconnected")&&!(!t&&((a=s.remote)==null?void 0:a.state)!=="connected")){if(typeof s.remote.prompt!="function"){console.warn("MediaChrome: Casting is not supported in this environment");return}s.remote.prompt().catch(()=>{})}},remoteEvents:["connect","connecting","disconnect"]},mediaIsAirplaying:{get(){return!1},set(t,e){const{media:i}=e;if(i){if(!(i.webkitShowPlaybackTargetPicker&&f.WebKitPlaybackTargetAvailabilityEvent)){console.error("MediaChrome: received a request to select AirPlay but AirPlay is not supported in this environment");return}i.webkitShowPlaybackTargetPicker()}},mediaEvents:["webkitcurrentplaybacktargetiswirelesschanged"]},mediaFullscreenUnavailable:{get(t){const{media:e}=t;if(!Am||!wl(e))return we.UNSUPPORTED}},mediaPipUnavailable:{get(t){const{media:e}=t;if(!ym||!xl(e))return we.UNSUPPORTED;if(e!=null&&e.disablePictureInPicture)return we.UNAVAILABLE}},mediaVolumeUnavailable:{get(t){const{media:e}=t;if(Ma===!1||(e==null?void 0:e.volume)==null)return we.UNSUPPORTED},stateOwnersUpdateHandlers:[t=>{Ma==null&&Im.then(e=>t(e?void 0:we.UNSUPPORTED))}]},mediaCastUnavailable:{get(t,{availability:e="not-available"}={}){var i;const{media:a}=t;if(!xm||!((i=a==null?void 0:a.remote)!=null&&i.state))return we.UNSUPPORTED;if(!(e==null||e==="available"))return we.UNAVAILABLE},stateOwnersUpdateHandlers:[(t,e)=>{var i;const{media:a}=e;return a?(a.disableRemotePlayback||a.hasAttribute("disableremoteplayback")||(i=a==null?void 0:a.remote)==null||i.watchAvailability(r=>{t({availability:r?"available":"not-available"})}).catch(r=>{r.name==="NotSupportedError"?t({availability:null}):t({availability:"not-available"})}),()=>{var r;(r=a==null?void 0:a.remote)==null||r.cancelWatchAvailability().catch(()=>{})}):void 0}]},mediaAirplayUnavailable:{get(t,e){if(!Tm)return we.UNSUPPORTED;if((e==null?void 0:e.availability)==="not-available")return we.UNAVAILABLE},mediaEvents:["webkitplaybacktargetavailabilitychanged"],stateOwnersUpdateHandlers:[(t,e)=>{var i;const{media:a}=e;return a?(a.disableRemotePlayback||a.hasAttribute("disableremoteplayback")||(i=a==null?void 0:a.remote)==null||i.watchAvailability(r=>{t({availability:r?"available":"not-available"})}).catch(r=>{r.name==="NotSupportedError"?t({availability:null}):t({availability:"not-available"})}),()=>{var r;(r=a==null?void 0:a.remote)==null||r.cancelWatchAvailability().catch(()=>{})}):void 0}]},mediaRenditionUnavailable:{get(t){var e;const{media:i}=t;if(!(i!=null&&i.videoRenditions))return we.UNSUPPORTED;if(!((e=i.videoRenditions)!=null&&e.length))return we.UNAVAILABLE},mediaEvents:["emptied","loadstart"],videoRenditionsEvents:["addrendition","removerendition"]},mediaAudioTrackUnavailable:{get(t){var e,i;const{media:a}=t;if(!(a!=null&&a.audioTracks))return we.UNSUPPORTED;if(((i=(e=a.audioTracks)==null?void 0:e.length)!=null?i:0)<=1)return we.UNAVAILABLE},mediaEvents:["emptied","loadstart"],audioTracksEvents:["addtrack","removetrack"]},mediaLang:{get(t){const{options:{mediaLang:e}={}}=t;return e??"en"}}},Lm={[w.MEDIA_PREVIEW_REQUEST](t,e,{detail:i}){var a,s,r;const{media:o}=e,l=i??void 0;let c,p;if(o&&l!=null){const[v]=Ga(o,{kind:Qe.METADATA,label:"thumbnails"}),g=Array.prototype.find.call((a=v==null?void 0:v.cues)!=null?a:[],(_,A,b)=>A===0?_.endTime>l:A===b.length-1?_.startTime<=l:_.startTime<=l&&_.endTime>l);if(g){const _=/'^(?:[a-z]+:)?\/\//i.test(g.text)||(s=o==null?void 0:o.querySelector('track[label="thumbnails"]'))==null?void 0:s.src,A=new URL(g.text,_);p=new URLSearchParams(A.hash).get("#xywh").split(",").map(T=>+T),c=A.href}}const u=t.mediaDuration.get(e);let m=(r=t.mediaChaptersCues.get(e).find((v,g,_)=>g===_.length-1&&u===v.endTime?v.startTime<=l&&v.endTime>=l:v.startTime<=l&&v.endTime>l))==null?void 0:r.text;return i!=null&&m==null&&(m=""),{mediaPreviewTime:l,mediaPreviewImage:c,mediaPreviewCoords:p,mediaPreviewChapter:m}},[w.MEDIA_PAUSE_REQUEST](t,e){t["mediaPaused"].set(!0,e)},[w.MEDIA_PLAY_REQUEST](t,e){var i,a,s,r;const o="mediaPaused",c=t.mediaStreamType.get(e)===et.LIVE,p=!((i=e.options)!=null&&i.noAutoSeekToLive),u=t.mediaTargetLiveWindow.get(e)>0;if(c&&p&&!u){const E=(a=t.mediaSeekable.get(e))==null?void 0:a[1];if(E){const m=(r=(s=e.options)==null?void 0:s.seekToLiveOffset)!=null?r:0,v=E-m;t.mediaCurrentTime.set(v,e)}}t[o].set(!1,e)},[w.MEDIA_PLAYBACK_RATE_REQUEST](t,e,{detail:i}){const a="mediaPlaybackRate",s=i;t[a].set(s,e)},[w.MEDIA_MUTE_REQUEST](t,e){t["mediaMuted"].set(!0,e)},[w.MEDIA_UNMUTE_REQUEST](t,e){const i="mediaMuted";t.mediaVolume.get(e)||t.mediaVolume.set(.25,e),t[i].set(!1,e)},[w.MEDIA_LOOP_REQUEST](t,e,{detail:i}){const a="mediaLoop",s=!!i;return t[a].set(s,e),{mediaLoop:s}},[w.MEDIA_VOLUME_REQUEST](t,e,{detail:i}){const a="mediaVolume",s=i;s&&t.mediaMuted.get(e)&&t.mediaMuted.set(!1,e),t[a].set(s,e)},[w.MEDIA_SEEK_REQUEST](t,e,{detail:i}){const a="mediaCurrentTime",s=i;t[a].set(s,e)},[w.MEDIA_SEEK_TO_LIVE_REQUEST](t,e){var i,a,s;const r="mediaCurrentTime",o=(i=t.mediaSeekable.get(e))==null?void 0:i[1];if(Number.isNaN(Number(o)))return;const l=(s=(a=e.options)==null?void 0:a.seekToLiveOffset)!=null?s:0,c=o-l;t[r].set(c,e)},[w.MEDIA_SHOW_SUBTITLES_REQUEST](t,e,{detail:i}){var a;const{options:s}=e,r=ka(e),o=yl(i),l=(a=o[0])==null?void 0:a.language;l&&!s.noSubtitlesLangPref&&f.localStorage.setItem("media-chrome-pref-subtitles-lang",l),Ti(Xt.SHOWING,r,o)},[w.MEDIA_DISABLE_SUBTITLES_REQUEST](t,e,{detail:i}){const a=ka(e),s=i??[];Ti(Xt.DISABLED,a,s)},[w.MEDIA_TOGGLE_SUBTITLES_REQUEST](t,e,{detail:i}){Il(e,i)},[w.MEDIA_RENDITION_REQUEST](t,e,{detail:i}){const a="mediaRenditionSelected",s=i;t[a].set(s,e)},[w.MEDIA_AUDIO_TRACK_REQUEST](t,e,{detail:i}){const a="mediaAudioTrackEnabled",s=i;t[a].set(s,e)},[w.MEDIA_ENTER_PIP_REQUEST](t,e){const i="mediaIsPip";t.mediaIsFullscreen.get(e)&&t.mediaIsFullscreen.set(!1,e),t[i].set(!0,e)},[w.MEDIA_EXIT_PIP_REQUEST](t,e){t["mediaIsPip"].set(!1,e)},[w.MEDIA_ENTER_FULLSCREEN_REQUEST](t,e,i){const a="mediaIsFullscreen";t.mediaIsPip.get(e)&&t.mediaIsPip.set(!1,e),t[a].set(!0,e,i)},[w.MEDIA_EXIT_FULLSCREEN_REQUEST](t,e){t["mediaIsFullscreen"].set(!1,e)},[w.MEDIA_ENTER_CAST_REQUEST](t,e){const i="mediaIsCasting";t.mediaIsFullscreen.get(e)&&t.mediaIsFullscreen.set(!1,e),t[i].set(!0,e)},[w.MEDIA_EXIT_CAST_REQUEST](t,e){t["mediaIsCasting"].set(!1,e)},[w.MEDIA_AIRPLAY_REQUEST](t,e){t["mediaIsAirplaying"].set(!0,e)}},Rm=({media:t,fullscreenElement:e,documentElement:i,stateMediator:a=mi,requestMap:s=Lm,options:r={},monitorStateOwnersOnlyWithSubscriptions:o=!0})=>{const l=[],c={options:{...r}};let p=Object.freeze({mediaPreviewTime:void 0,mediaPreviewImage:void 0,mediaPreviewCoords:void 0,mediaPreviewChapter:void 0});const u=_=>{_!=null&&(ln(_,p)||(p=Object.freeze({...p,..._}),l.forEach(A=>A(p))))},E=()=>{const _=Object.entries(a).reduce((A,[b,{get:T}])=>(A[b]=T(c),A),{});u(_)},m={};let v;const g=async(_,A)=>{var b,T,S,M,I,x,L,$,ie,R,H,ae,B,se,ne,N;const re=!!v;if(v={...c,...v??{},..._},re)return;await km(...Object.values(_));const U=l.length>0&&A===0&&o,O=c.media!==v.media,q=((b=c.media)==null?void 0:b.textTracks)!==((T=v.media)==null?void 0:T.textTracks),Te=((S=c.media)==null?void 0:S.videoRenditions)!==((M=v.media)==null?void 0:M.videoRenditions),pt=((I=c.media)==null?void 0:I.audioTracks)!==((x=v.media)==null?void 0:x.audioTracks),Mn=((L=c.media)==null?void 0:L.remote)!==(($=v.media)==null?void 0:$.remote),Cn=c.documentElement!==v.documentElement,Ln=!!c.media&&(O||U),Rn=!!((ie=c.media)!=null&&ie.textTracks)&&(q||U),Dn=!!((R=c.media)!=null&&R.videoRenditions)&&(Te||U),Nn=!!((H=c.media)!=null&&H.audioTracks)&&(pt||U),Pn=!!((ae=c.media)!=null&&ae.remote)&&(Mn||U),On=!!c.documentElement&&(Cn||U),hs=Ln||Rn||Dn||Nn||Pn||On,It=l.length===0&&A===1&&o,Un=!!v.media&&(O||It),$n=!!((B=v.media)!=null&&B.textTracks)&&(q||It),Hn=!!((se=v.media)!=null&&se.videoRenditions)&&(Te||It),jn=!!((ne=v.media)!=null&&ne.audioTracks)&&(pt||It),Fn=!!((N=v.media)!=null&&N.remote)&&(Mn||It),Wn=!!v.documentElement&&(Cn||It),Bn=Un||$n||Hn||jn||Fn||Wn;if(!(hs||Bn)){Object.entries(v).forEach(([Y,si])=>{c[Y]=si}),E(),v=void 0;return}Object.entries(a).forEach(([Y,{get:si,mediaEvents:ud=[],textTracksEvents:hd=[],videoRenditionsEvents:md=[],audioTracksEvents:pd=[],remoteEvents:fd=[],rootEvents:vd=[],stateOwnersUpdateHandlers:gd=[]}])=>{m[Y]||(m[Y]={});const xe=X=>{const le=si(c,X);u({[Y]:le})};let he;he=m[Y].mediaEvents,ud.forEach(X=>{he&&Ln&&(c.media.removeEventListener(X,he),m[Y].mediaEvents=void 0),Un&&(v.media.addEventListener(X,xe),m[Y].mediaEvents=xe)}),he=m[Y].textTracksEvents,hd.forEach(X=>{var le,Re;he&&Rn&&((le=c.media.textTracks)==null||le.removeEventListener(X,he),m[Y].textTracksEvents=void 0),$n&&((Re=v.media.textTracks)==null||Re.addEventListener(X,xe),m[Y].textTracksEvents=xe)}),he=m[Y].videoRenditionsEvents,md.forEach(X=>{var le,Re;he&&Dn&&((le=c.media.videoRenditions)==null||le.removeEventListener(X,he),m[Y].videoRenditionsEvents=void 0),Hn&&((Re=v.media.videoRenditions)==null||Re.addEventListener(X,xe),m[Y].videoRenditionsEvents=xe)}),he=m[Y].audioTracksEvents,pd.forEach(X=>{var le,Re;he&&Nn&&((le=c.media.audioTracks)==null||le.removeEventListener(X,he),m[Y].audioTracksEvents=void 0),jn&&((Re=v.media.audioTracks)==null||Re.addEventListener(X,xe),m[Y].audioTracksEvents=xe)}),he=m[Y].remoteEvents,fd.forEach(X=>{var le,Re;he&&Pn&&((le=c.media.remote)==null||le.removeEventListener(X,he),m[Y].remoteEvents=void 0),Fn&&((Re=v.media.remote)==null||Re.addEventListener(X,xe),m[Y].remoteEvents=xe)}),he=m[Y].rootEvents,vd.forEach(X=>{he&&On&&(c.documentElement.removeEventListener(X,he),m[Y].rootEvents=void 0),Wn&&(v.documentElement.addEventListener(X,xe),m[Y].rootEvents=xe)});const $i=m[Y].stateOwnersUpdateHandlers;if($i&&hs&&(Array.isArray($i)?$i:[$i]).forEach(le=>{typeof le=="function"&&le()}),Bn){const X=gd.map(le=>le(xe,v)).filter(le=>typeof le=="function");m[Y].stateOwnersUpdateHandlers=X.length===1?X[0]:X}else hs&&(m[Y].stateOwnersUpdateHandlers=void 0)}),Object.entries(v).forEach(([Y,si])=>{c[Y]=si}),E(),v=void 0};return g({media:t,fullscreenElement:e,documentElement:i,options:r}),{dispatch(_){const{type:A,detail:b}=_;if(s[A]&&p.mediaErrorCode==null){u(s[A](a,c,_));return}A==="mediaelementchangerequest"?g({media:b}):A==="fullscreenelementchangerequest"?g({fullscreenElement:b}):A==="documentelementchangerequest"?g({documentElement:b}):A==="optionschangerequest"&&(Object.entries(b??{}).forEach(([T,S])=>{c.options[T]=S}),E())},getState(){return p},subscribe(_){return g({},l.length+1),l.push(_),_(p),()=>{const A=l.indexOf(_);A>=0&&(g({},l.length-1),l.splice(A,1))}}}};var dn=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},C=(t,e,i)=>(dn(t,e,"read from private field"),i?i.call(t):e.get(t)),Me=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},We=(t,e,i,a)=>(dn(t,e,"write to private field"),e.set(t,i),i),ri=(t,e,i)=>(dn(t,e,"access private method"),i),ut,pi,W,At,fi,Be,ea,vi,ta,Ss,yt,ia,Is,ks,kl;const Ml=["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Enter"," ","f","m","k","c","l","j",">","<","p"],lr=10,dr=.025,cr=.25,Dm=.25,Nm=2,y={DEFAULT_SUBTITLES:"defaultsubtitles",DEFAULT_STREAM_TYPE:"defaultstreamtype",DEFAULT_DURATION:"defaultduration",FULLSCREEN_ELEMENT:"fullscreenelement",HOTKEYS:"hotkeys",KEYBOARD_BACKWARD_SEEK_OFFSET:"keyboardbackwardseekoffset",KEYBOARD_FORWARD_SEEK_OFFSET:"keyboardforwardseekoffset",KEYBOARD_DOWN_VOLUME_STEP:"keyboarddownvolumestep",KEYBOARD_UP_VOLUME_STEP:"keyboardupvolumestep",KEYS_USED:"keysused",LANG:"lang",LOOP:"loop",LIVE_EDGE_OFFSET:"liveedgeoffset",NO_AUTO_SEEK_TO_LIVE:"noautoseektolive",NO_DEFAULT_STORE:"nodefaultstore",NO_HOTKEYS:"nohotkeys",NO_MUTED_PREF:"nomutedpref",NO_SUBTITLES_LANG_PREF:"nosubtitleslangpref",NO_VOLUME_PREF:"novolumepref",SEEK_TO_LIVE_OFFSET:"seektoliveoffset"};let Cl=class extends Ui{constructor(){super(),Me(this,ta),Me(this,ia),Me(this,ks),this.mediaStateReceivers=[],this.associatedElementSubscriptions=new Map,Me(this,ut,new bl(this,y.HOTKEYS)),Me(this,pi,void 0),Me(this,W,void 0),Me(this,At,null),Me(this,fi,void 0),Me(this,Be,void 0),Me(this,ea,i=>{var a;(a=C(this,W))==null||a.dispatch(i)}),Me(this,vi,void 0),Me(this,yt,i=>{const{key:a,shiftKey:s}=i;if(!(s&&(a==="/"||a==="?")||Ml.includes(a))){this.removeEventListener("keyup",C(this,yt));return}this.keyboardShortcutHandler(i)}),this.associateElement(this);let e={};We(this,fi,i=>{Object.entries(i).forEach(([a,s])=>{if(a in e&&e[a]===s)return;this.propagateMediaState(a,s);const r=a.toLowerCase(),o=new f.CustomEvent(Nh[r],{composed:!0,detail:s});this.dispatchEvent(o)}),e=i}),this.hasAttribute(y.NO_HOTKEYS)?this.disableHotkeys():this.enableHotkeys()}static get observedAttributes(){return super.observedAttributes.concat(y.NO_HOTKEYS,y.HOTKEYS,y.DEFAULT_STREAM_TYPE,y.DEFAULT_SUBTITLES,y.DEFAULT_DURATION,y.NO_MUTED_PREF,y.NO_VOLUME_PREF,y.LANG,y.LOOP)}get mediaStore(){return C(this,W)}set mediaStore(e){var i,a;if(C(this,W)&&((i=C(this,Be))==null||i.call(this),We(this,Be,void 0)),We(this,W,e),!C(this,W)&&!this.hasAttribute(y.NO_DEFAULT_STORE)){ri(this,ta,Ss).call(this);return}We(this,Be,(a=C(this,W))==null?void 0:a.subscribe(C(this,fi)))}get fullscreenElement(){var e;return(e=C(this,pi))!=null?e:this}set fullscreenElement(e){var i;this.hasAttribute(y.FULLSCREEN_ELEMENT)&&this.removeAttribute(y.FULLSCREEN_ELEMENT),We(this,pi,e),(i=C(this,W))==null||i.dispatch({type:"fullscreenelementchangerequest",detail:this.fullscreenElement})}get defaultSubtitles(){return j(this,y.DEFAULT_SUBTITLES)}set defaultSubtitles(e){F(this,y.DEFAULT_SUBTITLES,e)}get defaultStreamType(){return ee(this,y.DEFAULT_STREAM_TYPE)}set defaultStreamType(e){te(this,y.DEFAULT_STREAM_TYPE,e)}get defaultDuration(){return J(this,y.DEFAULT_DURATION)}set defaultDuration(e){fe(this,y.DEFAULT_DURATION,e)}get noHotkeys(){return j(this,y.NO_HOTKEYS)}set noHotkeys(e){F(this,y.NO_HOTKEYS,e)}get keysUsed(){return ee(this,y.KEYS_USED)}set keysUsed(e){te(this,y.KEYS_USED,e)}get liveEdgeOffset(){return J(this,y.LIVE_EDGE_OFFSET)}set liveEdgeOffset(e){fe(this,y.LIVE_EDGE_OFFSET,e)}get noAutoSeekToLive(){return j(this,y.NO_AUTO_SEEK_TO_LIVE)}set noAutoSeekToLive(e){F(this,y.NO_AUTO_SEEK_TO_LIVE,e)}get noVolumePref(){return j(this,y.NO_VOLUME_PREF)}set noVolumePref(e){F(this,y.NO_VOLUME_PREF,e)}get noMutedPref(){return j(this,y.NO_MUTED_PREF)}set noMutedPref(e){F(this,y.NO_MUTED_PREF,e)}get noSubtitlesLangPref(){return j(this,y.NO_SUBTITLES_LANG_PREF)}set noSubtitlesLangPref(e){F(this,y.NO_SUBTITLES_LANG_PREF,e)}get noDefaultStore(){return j(this,y.NO_DEFAULT_STORE)}set noDefaultStore(e){F(this,y.NO_DEFAULT_STORE,e)}attributeChangedCallback(e,i,a){var s,r,o,l,c,p,u,E,m,v,g,_;if(super.attributeChangedCallback(e,i,a),e===y.NO_HOTKEYS)a!==i&&a===""?(this.hasAttribute(y.HOTKEYS)&&console.warn("Media Chrome: Both `hotkeys` and `nohotkeys` have been set. All hotkeys will be disabled."),this.disableHotkeys()):a!==i&&a===null&&this.enableHotkeys();else if(e===y.HOTKEYS)C(this,ut).value=a;else if(e===y.DEFAULT_SUBTITLES&&a!==i)(s=C(this,W))==null||s.dispatch({type:"optionschangerequest",detail:{defaultSubtitles:this.hasAttribute(y.DEFAULT_SUBTITLES)}});else if(e===y.DEFAULT_STREAM_TYPE)(o=C(this,W))==null||o.dispatch({type:"optionschangerequest",detail:{defaultStreamType:(r=this.getAttribute(y.DEFAULT_STREAM_TYPE))!=null?r:void 0}});else if(e===y.LIVE_EDGE_OFFSET)(l=C(this,W))==null||l.dispatch({type:"optionschangerequest",detail:{liveEdgeOffset:this.hasAttribute(y.LIVE_EDGE_OFFSET)?+this.getAttribute(y.LIVE_EDGE_OFFSET):void 0,seekToLiveOffset:this.hasAttribute(y.SEEK_TO_LIVE_OFFSET)?void 0:+this.getAttribute(y.LIVE_EDGE_OFFSET)}});else if(e===y.SEEK_TO_LIVE_OFFSET)(c=C(this,W))==null||c.dispatch({type:"optionschangerequest",detail:{seekToLiveOffset:this.hasAttribute(y.SEEK_TO_LIVE_OFFSET)?+this.getAttribute(y.SEEK_TO_LIVE_OFFSET):void 0}});else if(e===y.NO_AUTO_SEEK_TO_LIVE)(p=C(this,W))==null||p.dispatch({type:"optionschangerequest",detail:{noAutoSeekToLive:this.hasAttribute(y.NO_AUTO_SEEK_TO_LIVE)}});else if(e===y.FULLSCREEN_ELEMENT){const A=a?(u=this.getRootNode())==null?void 0:u.getElementById(a):void 0;We(this,pi,A),(E=C(this,W))==null||E.dispatch({type:"fullscreenelementchangerequest",detail:this.fullscreenElement})}else e===y.LANG&&a!==i?(Fh(a),(m=C(this,W))==null||m.dispatch({type:"optionschangerequest",detail:{mediaLang:a}})):e===y.LOOP&&a!==i?(v=C(this,W))==null||v.dispatch({type:w.MEDIA_LOOP_REQUEST,detail:a!=null}):e===y.NO_VOLUME_PREF&&a!==i?(g=C(this,W))==null||g.dispatch({type:"optionschangerequest",detail:{noVolumePref:this.hasAttribute(y.NO_VOLUME_PREF)}}):e===y.NO_MUTED_PREF&&a!==i&&((_=C(this,W))==null||_.dispatch({type:"optionschangerequest",detail:{noMutedPref:this.hasAttribute(y.NO_MUTED_PREF)}}))}connectedCallback(){var e,i;!C(this,W)&&!this.hasAttribute(y.NO_DEFAULT_STORE)&&ri(this,ta,Ss).call(this),(e=C(this,W))==null||e.dispatch({type:"documentelementchangerequest",detail:Ae}),super.connectedCallback(),C(this,W)&&!C(this,Be)&&We(this,Be,(i=C(this,W))==null?void 0:i.subscribe(C(this,fi))),C(this,vi)!==void 0&&C(this,W)&&this.media&&setTimeout(()=>{var a,s,r;(s=(a=this.media)==null?void 0:a.textTracks)!=null&&s.length&&((r=C(this,W))==null||r.dispatch({type:w.MEDIA_TOGGLE_SUBTITLES_REQUEST,detail:C(this,vi)}))},0),this.hasAttribute(y.NO_HOTKEYS)?this.disableHotkeys():this.enableHotkeys()}disconnectedCallback(){var e,i,a,s,r;if((e=super.disconnectedCallback)==null||e.call(this),this.disableHotkeys(),C(this,W)){const o=C(this,W).getState();We(this,vi,!!((i=o.mediaSubtitlesShowing)!=null&&i.length)),(a=C(this,W))==null||a.dispatch({type:"documentelementchangerequest",detail:void 0}),(s=C(this,W))==null||s.dispatch({type:w.MEDIA_TOGGLE_SUBTITLES_REQUEST,detail:!1})}C(this,Be)&&((r=C(this,Be))==null||r.call(this),We(this,Be,void 0)),this.unassociateElement(this)}mediaSetCallback(e){var i;super.mediaSetCallback(e),(i=C(this,W))==null||i.dispatch({type:"mediaelementchangerequest",detail:e}),e.hasAttribute("tabindex")||(e.tabIndex=-1)}mediaUnsetCallback(e){var i;super.mediaUnsetCallback(e),(i=C(this,W))==null||i.dispatch({type:"mediaelementchangerequest",detail:void 0})}propagateMediaState(e,i){mr(this.mediaStateReceivers,e,i)}associateElement(e){if(!e)return;const{associatedElementSubscriptions:i}=this;if(i.has(e))return;const a=this.registerMediaStateReceiver.bind(this),s=this.unregisterMediaStateReceiver.bind(this),r=jm(e,a,s);Object.values(w).forEach(o=>{e.addEventListener(o,C(this,ea))}),i.set(e,r)}unassociateElement(e){if(!e)return;const{associatedElementSubscriptions:i}=this;if(!i.has(e))return;i.get(e)(),i.delete(e),Object.values(w).forEach(s=>{e.removeEventListener(s,C(this,ea))})}registerMediaStateReceiver(e){if(!e)return;const i=this.mediaStateReceivers;i.indexOf(e)>-1||(i.push(e),C(this,W)&&Object.entries(C(this,W).getState()).forEach(([s,r])=>{mr([e],s,r)}))}unregisterMediaStateReceiver(e){const i=this.mediaStateReceivers,a=i.indexOf(e);a<0||i.splice(a,1)}enableHotkeys(){this.addEventListener("keydown",ri(this,ia,Is))}disableHotkeys(){this.removeEventListener("keydown",ri(this,ia,Is)),this.removeEventListener("keyup",C(this,yt))}get hotkeys(){return ee(this,y.HOTKEYS)}set hotkeys(e){te(this,y.HOTKEYS,e)}keyboardShortcutHandler(e){var i,a,s,r,o,l,c,p,u;const E=e.target;if(((s=(a=(i=E.getAttribute(y.KEYS_USED))==null?void 0:i.split(" "))!=null?a:E==null?void 0:E.keysUsed)!=null?s:[]).map(b=>b==="Space"?" ":b).filter(Boolean).includes(e.key))return;let v,g,_;if(!(C(this,ut).contains(`no${e.key.toLowerCase()}`)||e.key===" "&&C(this,ut).contains("nospace")||e.shiftKey&&(e.key==="/"||e.key==="?")&&C(this,ut).contains("noshift+/")))switch(e.key){case" ":case"k":v=C(this,W).getState().mediaPaused?w.MEDIA_PLAY_REQUEST:w.MEDIA_PAUSE_REQUEST,this.dispatchEvent(new f.CustomEvent(v,{composed:!0,bubbles:!0}));break;case"m":v=this.mediaStore.getState().mediaVolumeLevel==="off"?w.MEDIA_UNMUTE_REQUEST:w.MEDIA_MUTE_REQUEST,this.dispatchEvent(new f.CustomEvent(v,{composed:!0,bubbles:!0}));break;case"f":v=this.mediaStore.getState().mediaIsFullscreen?w.MEDIA_EXIT_FULLSCREEN_REQUEST:w.MEDIA_ENTER_FULLSCREEN_REQUEST,this.dispatchEvent(new f.CustomEvent(v,{composed:!0,bubbles:!0}));break;case"c":this.dispatchEvent(new f.CustomEvent(w.MEDIA_TOGGLE_SUBTITLES_REQUEST,{composed:!0,bubbles:!0}));break;case"ArrowLeft":case"j":{const b=this.hasAttribute(y.KEYBOARD_BACKWARD_SEEK_OFFSET)?+this.getAttribute(y.KEYBOARD_BACKWARD_SEEK_OFFSET):lr;g=Math.max(((r=this.mediaStore.getState().mediaCurrentTime)!=null?r:0)-b,0),_=new f.CustomEvent(w.MEDIA_SEEK_REQUEST,{composed:!0,bubbles:!0,detail:g}),this.dispatchEvent(_);break}case"ArrowRight":case"l":{const b=this.hasAttribute(y.KEYBOARD_FORWARD_SEEK_OFFSET)?+this.getAttribute(y.KEYBOARD_FORWARD_SEEK_OFFSET):lr;g=Math.max(((o=this.mediaStore.getState().mediaCurrentTime)!=null?o:0)+b,0),_=new f.CustomEvent(w.MEDIA_SEEK_REQUEST,{composed:!0,bubbles:!0,detail:g}),this.dispatchEvent(_);break}case"ArrowUp":{const b=this.hasAttribute(y.KEYBOARD_UP_VOLUME_STEP)?+this.getAttribute(y.KEYBOARD_UP_VOLUME_STEP):dr;g=Math.min(((l=this.mediaStore.getState().mediaVolume)!=null?l:1)+b,1),_=new f.CustomEvent(w.MEDIA_VOLUME_REQUEST,{composed:!0,bubbles:!0,detail:g}),this.dispatchEvent(_);break}case"ArrowDown":{const b=this.hasAttribute(y.KEYBOARD_DOWN_VOLUME_STEP)?+this.getAttribute(y.KEYBOARD_DOWN_VOLUME_STEP):dr;g=Math.max(((c=this.mediaStore.getState().mediaVolume)!=null?c:1)-b,0),_=new f.CustomEvent(w.MEDIA_VOLUME_REQUEST,{composed:!0,bubbles:!0,detail:g}),this.dispatchEvent(_);break}case"<":{const b=(p=this.mediaStore.getState().mediaPlaybackRate)!=null?p:1;g=Math.max(b-cr,Dm).toFixed(2),_=new f.CustomEvent(w.MEDIA_PLAYBACK_RATE_REQUEST,{composed:!0,bubbles:!0,detail:g}),this.dispatchEvent(_);break}case">":{const b=(u=this.mediaStore.getState().mediaPlaybackRate)!=null?u:1;g=Math.min(b+cr,Nm).toFixed(2),_=new f.CustomEvent(w.MEDIA_PLAYBACK_RATE_REQUEST,{composed:!0,bubbles:!0,detail:g}),this.dispatchEvent(_);break}case"/":case"?":{e.shiftKey&&ri(this,ks,kl).call(this);break}case"p":{v=this.mediaStore.getState().mediaIsPip?w.MEDIA_EXIT_PIP_REQUEST:w.MEDIA_ENTER_PIP_REQUEST,_=new f.CustomEvent(v,{composed:!0,bubbles:!0}),this.dispatchEvent(_);break}}}};ut=new WeakMap;pi=new WeakMap;W=new WeakMap;At=new WeakMap;fi=new WeakMap;Be=new WeakMap;ea=new WeakMap;vi=new WeakMap;ta=new WeakSet;Ss=function(){var t;this.mediaStore=Rm({media:this.media,fullscreenElement:this.fullscreenElement,options:{defaultSubtitles:this.hasAttribute(y.DEFAULT_SUBTITLES),defaultDuration:this.hasAttribute(y.DEFAULT_DURATION)?+this.getAttribute(y.DEFAULT_DURATION):void 0,defaultStreamType:(t=this.getAttribute(y.DEFAULT_STREAM_TYPE))!=null?t:void 0,liveEdgeOffset:this.hasAttribute(y.LIVE_EDGE_OFFSET)?+this.getAttribute(y.LIVE_EDGE_OFFSET):void 0,seekToLiveOffset:this.hasAttribute(y.SEEK_TO_LIVE_OFFSET)?+this.getAttribute(y.SEEK_TO_LIVE_OFFSET):this.hasAttribute(y.LIVE_EDGE_OFFSET)?+this.getAttribute(y.LIVE_EDGE_OFFSET):void 0,noAutoSeekToLive:this.hasAttribute(y.NO_AUTO_SEEK_TO_LIVE),noVolumePref:this.hasAttribute(y.NO_VOLUME_PREF),noMutedPref:this.hasAttribute(y.NO_MUTED_PREF),noSubtitlesLangPref:this.hasAttribute(y.NO_SUBTITLES_LANG_PREF)}})};yt=new WeakMap;ia=new WeakSet;Is=function(t){var e;const{metaKey:i,altKey:a,key:s,shiftKey:r}=t,o=r&&(s==="/"||s==="?");if(o&&((e=C(this,At))!=null&&e.open)){this.removeEventListener("keyup",C(this,yt));return}if(i||a||!o&&!Ml.includes(s)){this.removeEventListener("keyup",C(this,yt));return}const l=t.target,c=l instanceof HTMLElement&&(l.tagName.toLowerCase()==="media-volume-range"||l.tagName.toLowerCase()==="media-time-range");[" ","ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(s)&&!(C(this,ut).contains(`no${s.toLowerCase()}`)||s===" "&&C(this,ut).contains("nospace"))&&!c&&t.preventDefault(),this.addEventListener("keyup",C(this,yt),{once:!0})};ks=new WeakSet;kl=function(){C(this,At)||(We(this,At,Ae.createElement("media-keyboard-shortcuts-dialog")),this.appendChild(C(this,At))),C(this,At).open=!0};const Pm=Object.values(d),Om=Object.values(Zo),Ll=t=>{var e,i,a,s;let{observedAttributes:r}=t.constructor;!r&&((e=t.nodeName)!=null&&e.includes("-"))&&(f.customElements.upgrade(t),{observedAttributes:r}=t.constructor);const o=(s=(a=(i=t==null?void 0:t.getAttribute)==null?void 0:i.call(t,z.MEDIA_CHROME_ATTRIBUTES))==null?void 0:a.split)==null?void 0:s.call(a,/\s+/);return Array.isArray(r||o)?(r||o).filter(l=>Pm.includes(l)):[]},Um=t=>{var e,i;return(e=t.nodeName)!=null&&e.includes("-")&&f.customElements.get((i=t.nodeName)==null?void 0:i.toLowerCase())&&!(t instanceof f.customElements.get(t.nodeName.toLowerCase()))&&f.customElements.upgrade(t),Om.some(a=>a in t)},Ms=t=>Um(t)||!!Ll(t).length,ur=t=>{var e;return(e=t==null?void 0:t.join)==null?void 0:e.call(t,":")},hr={[d.MEDIA_SUBTITLES_LIST]:ws,[d.MEDIA_SUBTITLES_SHOWING]:ws,[d.MEDIA_SEEKABLE]:ur,[d.MEDIA_BUFFERED]:t=>t==null?void 0:t.map(ur).join(" "),[d.MEDIA_PREVIEW_COORDS]:t=>t==null?void 0:t.join(" "),[d.MEDIA_RENDITION_LIST]:Oh,[d.MEDIA_AUDIO_TRACK_LIST]:$h},$m=async(t,e,i)=>{var a,s;if(t.isConnected||await el(0),typeof i=="boolean"||i==null)return F(t,e,i);if(typeof i=="number")return fe(t,e,i);if(typeof i=="string")return te(t,e,i);if(Array.isArray(i)&&!i.length)return t.removeAttribute(e);const r=(s=(a=hr[e])==null?void 0:a.call(hr,i))!=null?s:i;return t.setAttribute(e,r)},Hm=t=>{var e;return!!((e=t.closest)!=null&&e.call(t,'*[slot="media"]'))},gt=(t,e)=>{if(Hm(t))return;const i=(s,r)=>{var o,l;Ms(s)&&r(s);const{children:c=[]}=s??{},p=(l=(o=s==null?void 0:s.shadowRoot)==null?void 0:o.children)!=null?l:[];[...c,...p].forEach(E=>gt(E,r))},a=t==null?void 0:t.nodeName.toLowerCase();if(a.includes("-")&&!Ms(t)){f.customElements.whenDefined(a).then(()=>{i(t,e)});return}i(t,e)},mr=(t,e,i)=>{t.forEach(a=>{if(e in a){a[e]=i;return}const s=Ll(a),r=e.toLowerCase();s.includes(r)&&$m(a,r,i)})},jm=(t,e,i)=>{gt(t,e);const a=u=>{var E;const m=(E=u==null?void 0:u.composedPath()[0])!=null?E:u.target;e(m)},s=u=>{var E;const m=(E=u==null?void 0:u.composedPath()[0])!=null?E:u.target;i(m)};t.addEventListener(w.REGISTER_MEDIA_STATE_RECEIVER,a),t.addEventListener(w.UNREGISTER_MEDIA_STATE_RECEIVER,s);const r=u=>{u.forEach(E=>{const{addedNodes:m=[],removedNodes:v=[],type:g,target:_,attributeName:A}=E;g==="childList"?(Array.prototype.forEach.call(m,b=>gt(b,e)),Array.prototype.forEach.call(v,b=>gt(b,i))):g==="attributes"&&A===z.MEDIA_CHROME_ATTRIBUTES&&(Ms(_)?e(_):i(_))})};let o=[];const l=u=>{const E=u.target;E.name!=="media"&&(o.forEach(m=>gt(m,i)),o=[...E.assignedElements({flatten:!0})],o.forEach(m=>gt(m,e)))};t.addEventListener("slotchange",l);const c=new MutationObserver(r);return c.observe(t,{childList:!0,attributes:!0,subtree:!0}),()=>{gt(t,i),t.removeEventListener("slotchange",l),c.disconnect(),t.removeEventListener(w.REGISTER_MEDIA_STATE_RECEIVER,a),t.removeEventListener(w.UNREGISTER_MEDIA_STATE_RECEIVER,s)}};f.customElements.get("media-controller")||f.customElements.define("media-controller",Cl);var Fm=Cl;const kt={PLACEMENT:"placement",BOUNDS:"bounds"};function Wm(t){return`
    <style>
      :host {
        --_tooltip-background-color: var(--media-tooltip-background-color, var(--media-secondary-color, rgba(20, 20, 30, .7)));
        --_tooltip-background: var(--media-tooltip-background, var(--_tooltip-background-color));
        --_tooltip-arrow-half-width: calc(var(--media-tooltip-arrow-width, 12px) / 2);
        --_tooltip-arrow-height: var(--media-tooltip-arrow-height, 5px);
        --_tooltip-arrow-background: var(--media-tooltip-arrow-color, var(--_tooltip-background-color));
        position: relative;
        pointer-events: none;
        display: var(--media-tooltip-display, inline-flex);
        justify-content: center;
        align-items: center;
        box-sizing: border-box;
        z-index: var(--media-tooltip-z-index, 1);
        background: var(--_tooltip-background);
        color: var(--media-text-color, var(--media-primary-color, rgb(238 238 238)));
        font: var(--media-font,
          var(--media-font-weight, 400)
          var(--media-font-size, 13px) /
          var(--media-text-content-height, var(--media-control-height, 18px))
          var(--media-font-family, helvetica neue, segoe ui, roboto, arial, sans-serif));
        padding: var(--media-tooltip-padding, .35em .7em);
        border: var(--media-tooltip-border, none);
        border-radius: var(--media-tooltip-border-radius, 5px);
        filter: var(--media-tooltip-filter, drop-shadow(0 0 4px rgba(0, 0, 0, .2)));
        white-space: var(--media-tooltip-white-space, nowrap);
      }

      :host([hidden]) {
        display: none;
      }

      img, svg {
        display: inline-block;
      }

      #arrow {
        position: absolute;
        width: 0px;
        height: 0px;
        border-style: solid;
        display: var(--media-tooltip-arrow-display, block);
      }

      :host(:not([placement])),
      :host([placement="top"]) {
        position: absolute;
        bottom: calc(100% + var(--media-tooltip-distance, 12px));
        left: 50%;
        transform: translate(calc(-50% - var(--media-tooltip-offset-x, 0px)), 0);
      }
      :host(:not([placement])) #arrow,
      :host([placement="top"]) #arrow {
        top: 100%;
        left: 50%;
        border-width: var(--_tooltip-arrow-height) var(--_tooltip-arrow-half-width) 0 var(--_tooltip-arrow-half-width);
        border-color: var(--_tooltip-arrow-background) transparent transparent transparent;
        transform: translate(calc(-50% + var(--media-tooltip-offset-x, 0px)), 0);
      }

      :host([placement="right"]) {
        position: absolute;
        left: calc(100% + var(--media-tooltip-distance, 12px));
        top: 50%;
        transform: translate(0, -50%);
      }
      :host([placement="right"]) #arrow {
        top: 50%;
        right: 100%;
        border-width: var(--_tooltip-arrow-half-width) var(--_tooltip-arrow-height) var(--_tooltip-arrow-half-width) 0;
        border-color: transparent var(--_tooltip-arrow-background) transparent transparent;
        transform: translate(0, -50%);
      }

      :host([placement="bottom"]) {
        position: absolute;
        top: calc(100% + var(--media-tooltip-distance, 12px));
        left: 50%;
        transform: translate(calc(-50% - var(--media-tooltip-offset-x, 0px)), 0);
      }
      :host([placement="bottom"]) #arrow {
        bottom: 100%;
        left: 50%;
        border-width: 0 var(--_tooltip-arrow-half-width) var(--_tooltip-arrow-height) var(--_tooltip-arrow-half-width);
        border-color: transparent transparent var(--_tooltip-arrow-background) transparent;
        transform: translate(calc(-50% + var(--media-tooltip-offset-x, 0px)), 0);
      }

      :host([placement="left"]) {
        position: absolute;
        right: calc(100% + var(--media-tooltip-distance, 12px));
        top: 50%;
        transform: translate(0, -50%);
      }
      :host([placement="left"]) #arrow {
        top: 50%;
        left: 100%;
        border-width: var(--_tooltip-arrow-half-width) 0 var(--_tooltip-arrow-half-width) var(--_tooltip-arrow-height);
        border-color: transparent transparent transparent var(--_tooltip-arrow-background);
        transform: translate(0, -50%);
      }
      
      :host([placement="none"]) #arrow {
        display: none;
      }
    </style>
    <slot></slot>
    <div id="arrow"></div>
  `}class Ka extends f.HTMLElement{constructor(){if(super(),this.updateXOffset=()=>{var e;if(!hl(this,{checkOpacity:!1,checkVisibilityCSS:!1}))return;const i=this.placement;if(i==="left"||i==="right"){this.style.removeProperty("--media-tooltip-offset-x");return}const a=getComputedStyle(this),s=(e=Oi(this,"#"+this.bounds))!=null?e:Gh(this);if(!s)return;const{x:r,width:o}=s.getBoundingClientRect(),{x:l,width:c}=this.getBoundingClientRect(),p=l+c,u=r+o,E=a.getPropertyValue("--media-tooltip-offset-x"),m=E?parseFloat(E.replace("px","")):0,v=a.getPropertyValue("--media-tooltip-container-margin"),g=v?parseFloat(v.replace("px","")):0,_=l-r+m-g,A=p-u+m+g;if(_<0){this.style.setProperty("--media-tooltip-offset-x",`${_}px`);return}if(A>0){this.style.setProperty("--media-tooltip-offset-x",`${A}px`);return}this.style.removeProperty("--media-tooltip-offset-x")},!this.shadowRoot){this.attachShadow(this.constructor.shadowRootOptions);const e=$e(this.attributes);this.shadowRoot.innerHTML=this.constructor.getTemplateHTML(e)}if(this.arrowEl=this.shadowRoot.querySelector("#arrow"),Object.prototype.hasOwnProperty.call(this,"placement")){const e=this.placement;delete this.placement,this.placement=e}}static get observedAttributes(){return[kt.PLACEMENT,kt.BOUNDS]}get placement(){return ee(this,kt.PLACEMENT)}set placement(e){te(this,kt.PLACEMENT,e)}get bounds(){return ee(this,kt.BOUNDS)}set bounds(e){te(this,kt.BOUNDS,e)}}Ka.shadowRootOptions={mode:"open"};Ka.getTemplateHTML=Wm;f.customElements.get("media-tooltip")||f.customElements.define("media-tooltip",Ka);var Cs=Ka,cn=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},de=(t,e,i)=>(cn(t,e,"read from private field"),i?i.call(t):e.get(t)),Mt=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},Bi=(t,e,i,a)=>(cn(t,e,"write to private field"),e.set(t,i),i),Bm=(t,e,i)=>(cn(t,e,"access private method"),i),Ve,Yt,ht,Ut,aa,Ls,Rl;const at={TOOLTIP_PLACEMENT:"tooltipplacement",DISABLED:"disabled",NO_TOOLTIP:"notooltip"};function Vm(t,e={}){return`
    <style>
      :host {
        position: relative;
        font: var(--media-font,
          var(--media-font-weight, bold)
          var(--media-font-size, 14px) /
          var(--media-text-content-height, var(--media-control-height, 24px))
          var(--media-font-family, helvetica neue, segoe ui, roboto, arial, sans-serif));
        color: var(--media-text-color, var(--media-primary-color, rgb(238 238 238)));
        background: var(--media-control-background, var(--media-secondary-color, rgb(20 20 30 / .7)));
        padding: var(--media-button-padding, var(--media-control-padding, 10px));
        justify-content: var(--media-button-justify-content, center);
        display: inline-flex;
        align-items: center;
        vertical-align: middle;
        box-sizing: border-box;
        transition: background .15s linear;
        pointer-events: auto;
        cursor: var(--media-cursor, pointer);
        -webkit-tap-highlight-color: transparent;
      }

      
      :host(:focus-visible) {
        box-shadow: var(--media-focus-box-shadow, inset 0 0 0 2px rgb(27 127 204 / .9));
        outline: 0;
      }
      
      :host(:where(:focus)) {
        box-shadow: none;
        outline: 0;
      }

      :host(:hover) {
        background: var(--media-control-hover-background, rgba(50 50 70 / .7));
      }

      svg, img, ::slotted(svg), ::slotted(img) {
        width: var(--media-button-icon-width);
        height: var(--media-button-icon-height, var(--media-control-height, 24px));
        transform: var(--media-button-icon-transform);
        transition: var(--media-button-icon-transition);
        fill: var(--media-icon-color, var(--media-primary-color, rgb(238 238 238)));
        vertical-align: middle;
        max-width: 100%;
        max-height: 100%;
        min-width: 100%;
      }

      media-tooltip {
        
        max-width: 0;
        overflow-x: clip;
        opacity: 0;
        transition: opacity .3s, max-width 0s 9s;
      }

      :host(:hover) media-tooltip,
      :host(:focus-visible) media-tooltip {
        max-width: 100vw;
        opacity: 1;
        transition: opacity .3s;
      }

      :host([notooltip]) slot[name="tooltip"] {
        display: none;
      }
    </style>

    ${this.getSlotTemplateHTML(t,e)}

    <slot name="tooltip">
      <media-tooltip part="tooltip" aria-hidden="true">
        <template shadowrootmode="${Cs.shadowRootOptions.mode}">
          ${Cs.getTemplateHTML({})}
        </template>
        <slot name="tooltip-content">
          ${this.getTooltipContentHTML(t)}
        </slot>
      </media-tooltip>
    </slot>
  `}function Gm(t,e){return`
    <slot></slot>
  `}function Km(){return""}class ve extends f.HTMLElement{constructor(){if(super(),Mt(this,Ls),Mt(this,Ve,void 0),this.preventClick=!1,this.tooltipEl=null,Mt(this,Yt,e=>{this.preventClick||this.handleClick(e),setTimeout(de(this,ht),0)}),Mt(this,ht,()=>{var e,i;(i=(e=this.tooltipEl)==null?void 0:e.updateXOffset)==null||i.call(e)}),Mt(this,Ut,e=>{const{key:i}=e;if(!this.keysUsed.includes(i)){this.removeEventListener("keyup",de(this,Ut));return}this.preventClick||this.handleClick(e)}),Mt(this,aa,e=>{const{metaKey:i,altKey:a,key:s}=e;if(i||a||!this.keysUsed.includes(s)){this.removeEventListener("keyup",de(this,Ut));return}this.addEventListener("keyup",de(this,Ut),{once:!0})}),!this.shadowRoot){this.attachShadow(this.constructor.shadowRootOptions);const e=$e(this.attributes),i=this.constructor.getTemplateHTML(e);this.shadowRoot.setHTMLUnsafe?this.shadowRoot.setHTMLUnsafe(i):this.shadowRoot.innerHTML=i}this.tooltipEl=this.shadowRoot.querySelector("media-tooltip")}static get observedAttributes(){return["disabled",at.TOOLTIP_PLACEMENT,z.MEDIA_CONTROLLER,d.MEDIA_LANG]}enable(){this.addEventListener("click",de(this,Yt)),this.addEventListener("keydown",de(this,aa)),this.tabIndex=0}disable(){this.removeEventListener("click",de(this,Yt)),this.removeEventListener("keydown",de(this,aa)),this.removeEventListener("keyup",de(this,Ut)),this.tabIndex=-1}attributeChangedCallback(e,i,a){var s,r,o,l,c;e===z.MEDIA_CONTROLLER?(i&&((r=(s=de(this,Ve))==null?void 0:s.unassociateElement)==null||r.call(s,this),Bi(this,Ve,null)),a&&this.isConnected&&(Bi(this,Ve,(o=this.getRootNode())==null?void 0:o.getElementById(a)),(c=(l=de(this,Ve))==null?void 0:l.associateElement)==null||c.call(l,this))):e==="disabled"&&a!==i?a==null?this.enable():this.disable():e===at.TOOLTIP_PLACEMENT&&this.tooltipEl&&a!==i?this.tooltipEl.placement=a:e===d.MEDIA_LANG&&(this.shadowRoot.querySelector('slot[name="tooltip-content"]').innerHTML=this.constructor.getTooltipContentHTML()),de(this,ht).call(this)}connectedCallback(){var e,i,a;const{style:s}=ue(this.shadowRoot,":host");s.setProperty("display",`var(--media-control-display, var(--${this.localName}-display, inline-flex))`),this.hasAttribute("disabled")?this.disable():this.enable(),this.setAttribute("role","button");const r=this.getAttribute(z.MEDIA_CONTROLLER);r&&(Bi(this,Ve,(e=this.getRootNode())==null?void 0:e.getElementById(r)),(a=(i=de(this,Ve))==null?void 0:i.associateElement)==null||a.call(i,this)),f.customElements.whenDefined("media-tooltip").then(()=>Bm(this,Ls,Rl).call(this))}disconnectedCallback(){var e,i;this.disable(),(i=(e=de(this,Ve))==null?void 0:e.unassociateElement)==null||i.call(e,this),Bi(this,Ve,null),this.removeEventListener("mouseenter",de(this,ht)),this.removeEventListener("focus",de(this,ht)),this.removeEventListener("click",de(this,Yt))}get keysUsed(){return["Enter"," "]}get tooltipPlacement(){return ee(this,at.TOOLTIP_PLACEMENT)}set tooltipPlacement(e){te(this,at.TOOLTIP_PLACEMENT,e)}get mediaController(){return ee(this,z.MEDIA_CONTROLLER)}set mediaController(e){te(this,z.MEDIA_CONTROLLER,e)}get disabled(){return j(this,at.DISABLED)}set disabled(e){F(this,at.DISABLED,e)}get noTooltip(){return j(this,at.NO_TOOLTIP)}set noTooltip(e){F(this,at.NO_TOOLTIP,e)}handleClick(e){}}Ve=new WeakMap;Yt=new WeakMap;ht=new WeakMap;Ut=new WeakMap;aa=new WeakMap;Ls=new WeakSet;Rl=function(){this.addEventListener("mouseenter",de(this,ht)),this.addEventListener("focus",de(this,ht)),this.addEventListener("click",de(this,Yt));const t=this.tooltipPlacement;t&&this.tooltipEl&&(this.tooltipEl.placement=t)};ve.shadowRootOptions={mode:"open"};ve.getTemplateHTML=Vm;ve.getSlotTemplateHTML=Gm;ve.getTooltipContentHTML=Km;f.customElements.get("media-chrome-button")||f.customElements.define("media-chrome-button",ve);var zm=ve;const pr=`<svg aria-hidden="true" viewBox="0 0 26 24">
  <path d="M22.13 3H3.87a.87.87 0 0 0-.87.87v13.26a.87.87 0 0 0 .87.87h3.4L9 16H5V5h16v11h-4l1.72 2h3.4a.87.87 0 0 0 .87-.87V3.87a.87.87 0 0 0-.86-.87Zm-8.75 11.44a.5.5 0 0 0-.76 0l-4.91 5.73a.5.5 0 0 0 .38.83h9.82a.501.501 0 0 0 .38-.83l-4.91-5.73Z"/>
</svg>
`;function qm(t){return`
    <style>
      :host([${d.MEDIA_IS_AIRPLAYING}]) slot[name=icon] slot:not([name=exit]) {
        display: none !important;
      }

      
      :host(:not([${d.MEDIA_IS_AIRPLAYING}])) slot[name=icon] slot:not([name=enter]) {
        display: none !important;
      }

      :host([${d.MEDIA_IS_AIRPLAYING}]) slot[name=tooltip-enter],
      :host(:not([${d.MEDIA_IS_AIRPLAYING}])) slot[name=tooltip-exit] {
        display: none;
      }
    </style>

    <slot name="icon">
      <slot name="enter">${pr}</slot>
      <slot name="exit">${pr}</slot>
    </slot>
  `}function Ym(){return`
    <slot name="tooltip-enter">${k("start airplay")}</slot>
    <slot name="tooltip-exit">${k("stop airplay")}</slot>
  `}const fr=t=>{const e=t.mediaIsAirplaying?k("stop airplay"):k("start airplay");t.setAttribute("aria-label",e)};class za extends ve{static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_IS_AIRPLAYING,d.MEDIA_AIRPLAY_UNAVAILABLE]}connectedCallback(){super.connectedCallback(),fr(this)}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),e===d.MEDIA_IS_AIRPLAYING&&fr(this)}get mediaIsAirplaying(){return j(this,d.MEDIA_IS_AIRPLAYING)}set mediaIsAirplaying(e){F(this,d.MEDIA_IS_AIRPLAYING,e)}get mediaAirplayUnavailable(){return ee(this,d.MEDIA_AIRPLAY_UNAVAILABLE)}set mediaAirplayUnavailable(e){te(this,d.MEDIA_AIRPLAY_UNAVAILABLE,e)}handleClick(){const e=new f.CustomEvent(w.MEDIA_AIRPLAY_REQUEST,{composed:!0,bubbles:!0});this.dispatchEvent(e)}}za.getSlotTemplateHTML=qm;za.getTooltipContentHTML=Ym;f.customElements.get("media-airplay-button")||f.customElements.define("media-airplay-button",za);var Qm=za;const Xm=`<svg aria-hidden="true" viewBox="0 0 26 24">
  <path d="M22.83 5.68a2.58 2.58 0 0 0-2.3-2.5c-3.62-.24-11.44-.24-15.06 0a2.58 2.58 0 0 0-2.3 2.5c-.23 4.21-.23 8.43 0 12.64a2.58 2.58 0 0 0 2.3 2.5c3.62.24 11.44.24 15.06 0a2.58 2.58 0 0 0 2.3-2.5c.23-4.21.23-8.43 0-12.64Zm-11.39 9.45a3.07 3.07 0 0 1-1.91.57 3.06 3.06 0 0 1-2.34-1 3.75 3.75 0 0 1-.92-2.67 3.92 3.92 0 0 1 .92-2.77 3.18 3.18 0 0 1 2.43-1 2.94 2.94 0 0 1 2.13.78c.364.359.62.813.74 1.31l-1.43.35a1.49 1.49 0 0 0-1.51-1.17 1.61 1.61 0 0 0-1.29.58 2.79 2.79 0 0 0-.5 1.89 3 3 0 0 0 .49 1.93 1.61 1.61 0 0 0 1.27.58 1.48 1.48 0 0 0 1-.37 2.1 2.1 0 0 0 .59-1.14l1.4.44a3.23 3.23 0 0 1-1.07 1.69Zm7.22 0a3.07 3.07 0 0 1-1.91.57 3.06 3.06 0 0 1-2.34-1 3.75 3.75 0 0 1-.92-2.67 3.88 3.88 0 0 1 .93-2.77 3.14 3.14 0 0 1 2.42-1 3 3 0 0 1 2.16.82 2.8 2.8 0 0 1 .73 1.31l-1.43.35a1.49 1.49 0 0 0-1.51-1.21 1.61 1.61 0 0 0-1.29.58A2.79 2.79 0 0 0 15 12a3 3 0 0 0 .49 1.93 1.61 1.61 0 0 0 1.27.58 1.44 1.44 0 0 0 1-.37 2.1 2.1 0 0 0 .6-1.15l1.4.44a3.17 3.17 0 0 1-1.1 1.7Z"/>
</svg>`,Zm=`<svg aria-hidden="true" viewBox="0 0 26 24">
  <path d="M17.73 14.09a1.4 1.4 0 0 1-1 .37 1.579 1.579 0 0 1-1.27-.58A3 3 0 0 1 15 12a2.8 2.8 0 0 1 .5-1.85 1.63 1.63 0 0 1 1.29-.57 1.47 1.47 0 0 1 1.51 1.2l1.43-.34A2.89 2.89 0 0 0 19 9.07a3 3 0 0 0-2.14-.78 3.14 3.14 0 0 0-2.42 1 3.91 3.91 0 0 0-.93 2.78 3.74 3.74 0 0 0 .92 2.66 3.07 3.07 0 0 0 2.34 1 3.07 3.07 0 0 0 1.91-.57 3.17 3.17 0 0 0 1.07-1.74l-1.4-.45c-.083.43-.3.822-.62 1.12Zm-7.22 0a1.43 1.43 0 0 1-1 .37 1.58 1.58 0 0 1-1.27-.58A3 3 0 0 1 7.76 12a2.8 2.8 0 0 1 .5-1.85 1.63 1.63 0 0 1 1.29-.57 1.47 1.47 0 0 1 1.51 1.2l1.43-.34a2.81 2.81 0 0 0-.74-1.32 2.94 2.94 0 0 0-2.13-.78 3.18 3.18 0 0 0-2.43 1 4 4 0 0 0-.92 2.78 3.74 3.74 0 0 0 .92 2.66 3.07 3.07 0 0 0 2.34 1 3.07 3.07 0 0 0 1.91-.57 3.23 3.23 0 0 0 1.07-1.74l-1.4-.45a2.06 2.06 0 0 1-.6 1.07Zm12.32-8.41a2.59 2.59 0 0 0-2.3-2.51C18.72 3.05 15.86 3 13 3c-2.86 0-5.72.05-7.53.17a2.59 2.59 0 0 0-2.3 2.51c-.23 4.207-.23 8.423 0 12.63a2.57 2.57 0 0 0 2.3 2.5c1.81.13 4.67.19 7.53.19 2.86 0 5.72-.06 7.53-.19a2.57 2.57 0 0 0 2.3-2.5c.23-4.207.23-8.423 0-12.63Zm-1.49 12.53a1.11 1.11 0 0 1-.91 1.11c-1.67.11-4.45.18-7.43.18-2.98 0-5.76-.07-7.43-.18a1.11 1.11 0 0 1-.91-1.11c-.21-4.14-.21-8.29 0-12.43a1.11 1.11 0 0 1 .91-1.11C7.24 4.56 10 4.49 13 4.49s5.76.07 7.43.18a1.11 1.11 0 0 1 .91 1.11c.21 4.14.21 8.29 0 12.43Z"/>
</svg>`;function Jm(t){return`
    <style>
      :host([aria-checked="true"]) slot[name=off] {
        display: none !important;
      }

      
      :host(:not([aria-checked="true"])) slot[name=on] {
        display: none !important;
      }

      :host([aria-checked="true"]) slot[name=tooltip-enable],
      :host(:not([aria-checked="true"])) slot[name=tooltip-disable] {
        display: none;
      }
    </style>

    <slot name="icon">
      <slot name="on">${Xm}</slot>
      <slot name="off">${Zm}</slot>
    </slot>
  `}function ep(){return`
    <slot name="tooltip-enable">${k("Enable captions")}</slot>
    <slot name="tooltip-disable">${k("Disable captions")}</slot>
  `}const vr=t=>{t.setAttribute("aria-checked",cm(t).toString())};class qa extends ve{static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_SUBTITLES_LIST,d.MEDIA_SUBTITLES_SHOWING]}connectedCallback(){super.connectedCallback(),this.setAttribute("role","button"),this.setAttribute("aria-label",k("closed captions")),vr(this)}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),e===d.MEDIA_SUBTITLES_SHOWING&&vr(this)}get mediaSubtitlesList(){return gr(this,d.MEDIA_SUBTITLES_LIST)}set mediaSubtitlesList(e){Er(this,d.MEDIA_SUBTITLES_LIST,e)}get mediaSubtitlesShowing(){return gr(this,d.MEDIA_SUBTITLES_SHOWING)}set mediaSubtitlesShowing(e){Er(this,d.MEDIA_SUBTITLES_SHOWING,e)}handleClick(){this.dispatchEvent(new f.CustomEvent(w.MEDIA_TOGGLE_SUBTITLES_REQUEST,{composed:!0,bubbles:!0}))}}qa.getSlotTemplateHTML=Jm;qa.getTooltipContentHTML=ep;const gr=(t,e)=>{const i=t.getAttribute(e);return i?Al(i):[]},Er=(t,e,i)=>{if(!(i!=null&&i.length)){t.removeAttribute(e);return}const a=ws(i);t.getAttribute(e)!==a&&t.setAttribute(e,a)};f.customElements.get("media-captions-button")||f.customElements.define("media-captions-button",qa);var tp=qa;const ip='<svg aria-hidden="true" viewBox="0 0 24 24"><g><path class="cast_caf_icon_arch0" d="M1,18 L1,21 L4,21 C4,19.3 2.66,18 1,18 L1,18 Z"/><path class="cast_caf_icon_arch1" d="M1,14 L1,16 C3.76,16 6,18.2 6,21 L8,21 C8,17.13 4.87,14 1,14 L1,14 Z"/><path class="cast_caf_icon_arch2" d="M1,10 L1,12 C5.97,12 10,16.0 10,21 L12,21 C12,14.92 7.07,10 1,10 L1,10 Z"/><path class="cast_caf_icon_box" d="M21,3 L3,3 C1.9,3 1,3.9 1,5 L1,8 L3,8 L3,5 L21,5 L21,19 L14,19 L14,21 L21,21 C22.1,21 23,20.1 23,19 L23,5 C23,3.9 22.1,3 21,3 L21,3 Z"/></g></svg>',ap='<svg aria-hidden="true" viewBox="0 0 24 24"><g><path class="cast_caf_icon_arch0" d="M1,18 L1,21 L4,21 C4,19.3 2.66,18 1,18 L1,18 Z"/><path class="cast_caf_icon_arch1" d="M1,14 L1,16 C3.76,16 6,18.2 6,21 L8,21 C8,17.13 4.87,14 1,14 L1,14 Z"/><path class="cast_caf_icon_arch2" d="M1,10 L1,12 C5.97,12 10,16.0 10,21 L12,21 C12,14.92 7.07,10 1,10 L1,10 Z"/><path class="cast_caf_icon_box" d="M21,3 L3,3 C1.9,3 1,3.9 1,5 L1,8 L3,8 L3,5 L21,5 L21,19 L14,19 L14,21 L21,21 C22.1,21 23,20.1 23,19 L23,5 C23,3.9 22.1,3 21,3 L21,3 Z"/><path class="cast_caf_icon_boxfill" d="M5,7 L5,8.63 C8,8.6 13.37,14 13.37,17 L19,17 L19,7 Z"/></g></svg>';function sp(t){return`
    <style>
      :host([${d.MEDIA_IS_CASTING}]) slot[name=icon] slot:not([name=exit]) {
        display: none !important;
      }

      
      :host(:not([${d.MEDIA_IS_CASTING}])) slot[name=icon] slot:not([name=enter]) {
        display: none !important;
      }

      :host([${d.MEDIA_IS_CASTING}]) slot[name=tooltip-enter],
      :host(:not([${d.MEDIA_IS_CASTING}])) slot[name=tooltip-exit] {
        display: none;
      }
    </style>

    <slot name="icon">
      <slot name="enter">${ip}</slot>
      <slot name="exit">${ap}</slot>
    </slot>
  `}function np(){return`
    <slot name="tooltip-enter">${k("Start casting")}</slot>
    <slot name="tooltip-exit">${k("Stop casting")}</slot>
  `}const br=t=>{const e=t.mediaIsCasting?k("stop casting"):k("start casting");t.setAttribute("aria-label",e)};class Ya extends ve{static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_IS_CASTING,d.MEDIA_CAST_UNAVAILABLE]}connectedCallback(){super.connectedCallback(),br(this)}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),e===d.MEDIA_IS_CASTING&&br(this)}get mediaIsCasting(){return j(this,d.MEDIA_IS_CASTING)}set mediaIsCasting(e){F(this,d.MEDIA_IS_CASTING,e)}get mediaCastUnavailable(){return ee(this,d.MEDIA_CAST_UNAVAILABLE)}set mediaCastUnavailable(e){te(this,d.MEDIA_CAST_UNAVAILABLE,e)}handleClick(){const e=this.mediaIsCasting?w.MEDIA_EXIT_CAST_REQUEST:w.MEDIA_ENTER_CAST_REQUEST;this.dispatchEvent(new f.CustomEvent(e,{composed:!0,bubbles:!0}))}}Ya.getSlotTemplateHTML=sp;Ya.getTooltipContentHTML=np;f.customElements.get("media-cast-button")||f.customElements.define("media-cast-button",Ya);var rp=Ya,un=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},Tt=(t,e,i)=>(un(t,e,"read from private field"),e.get(t)),Ze=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},hn=(t,e,i,a)=>(un(t,e,"write to private field"),e.set(t,i),i),ft=(t,e,i)=>(un(t,e,"access private method"),i),Ca,Ci,xt,sa,Rs,Ds,Dl,Ns,Nl,Ps,Pl,Os,Ol,Us,Ul;function op(t){return`
    <style>
      :host {
        font: var(--media-font,
          var(--media-font-weight, normal)
          var(--media-font-size, 14px) /
          var(--media-text-content-height, var(--media-control-height, 24px))
          var(--media-font-family, helvetica neue, segoe ui, roboto, arial, sans-serif));
        color: var(--media-text-color, var(--media-primary-color, rgb(238 238 238)));
        display: var(--media-dialog-display, inline-flex);
        justify-content: center;
        align-items: center;
        
        transition-behavior: allow-discrete;
        visibility: hidden;
        opacity: 0;
        transform: translateY(2px) scale(.99);
        pointer-events: none;
      }

      :host([open]) {
        transition: display .2s, visibility 0s, opacity .2s ease-out, transform .15s ease-out;
        visibility: visible;
        opacity: 1;
        transform: translateY(0) scale(1);
        pointer-events: auto;
      }

      #content {
        display: flex;
        position: relative;
        box-sizing: border-box;
        width: min(320px, 100%);
        word-wrap: break-word;
        max-height: 100%;
        overflow: auto;
        text-align: center;
        line-height: 1.4;
      }
    </style>
    ${this.getSlotTemplateHTML(t)}
  `}function lp(t){return`
    <slot id="content"></slot>
  `}const oi={OPEN:"open",ANCHOR:"anchor"};class wt extends f.HTMLElement{constructor(){super(),Ze(this,sa),Ze(this,Ds),Ze(this,Ns),Ze(this,Ps),Ze(this,Os),Ze(this,Us),Ze(this,Ca,!1),Ze(this,Ci,null),Ze(this,xt,null)}static get observedAttributes(){return[oi.OPEN,oi.ANCHOR]}get open(){return j(this,oi.OPEN)}set open(e){F(this,oi.OPEN,e)}handleEvent(e){switch(e.type){case"invoke":ft(this,Ps,Pl).call(this,e);break;case"focusout":ft(this,Os,Ol).call(this,e);break;case"keydown":ft(this,Us,Ul).call(this,e);break}}connectedCallback(){ft(this,sa,Rs).call(this),this.role||(this.role="dialog"),this.addEventListener("invoke",this),this.addEventListener("focusout",this),this.addEventListener("keydown",this)}disconnectedCallback(){this.removeEventListener("invoke",this),this.removeEventListener("focusout",this),this.removeEventListener("keydown",this)}attributeChangedCallback(e,i,a){ft(this,sa,Rs).call(this),e===oi.OPEN&&a!==i&&(this.open?ft(this,Ds,Dl).call(this):ft(this,Ns,Nl).call(this))}focus(){hn(this,Ci,ul());const e=!this.dispatchEvent(new Event("focus",{composed:!0,cancelable:!0})),i=!this.dispatchEvent(new Event("focusin",{composed:!0,bubbles:!0,cancelable:!0}));if(e||i)return;const a=this.querySelector('[autofocus], [tabindex]:not([tabindex="-1"]), [role="menu"]');a==null||a.focus()}get keysUsed(){return["Escape","Tab"]}}Ca=new WeakMap;Ci=new WeakMap;xt=new WeakMap;sa=new WeakSet;Rs=function(){if(!Tt(this,Ca)&&(hn(this,Ca,!0),!this.shadowRoot)){this.attachShadow(this.constructor.shadowRootOptions);const t=$e(this.attributes);this.shadowRoot.innerHTML=this.constructor.getTemplateHTML(t),queueMicrotask(()=>{const{style:e}=ue(this.shadowRoot,":host");e.setProperty("transition","display .15s, visibility .15s, opacity .15s ease-in, transform .15s ease-in")})}};Ds=new WeakSet;Dl=function(){var t;(t=Tt(this,xt))==null||t.setAttribute("aria-expanded","true"),this.dispatchEvent(new Event("open",{composed:!0,bubbles:!0})),this.addEventListener("transitionend",()=>this.focus(),{once:!0})};Ns=new WeakSet;Nl=function(){var t;(t=Tt(this,xt))==null||t.setAttribute("aria-expanded","false"),this.dispatchEvent(new Event("close",{composed:!0,bubbles:!0}))};Ps=new WeakSet;Pl=function(t){hn(this,xt,t.relatedTarget),ai(this,t.relatedTarget)||(this.open=!this.open)};Os=new WeakSet;Ol=function(t){var e;ai(this,t.relatedTarget)||((e=Tt(this,Ci))==null||e.focus(),Tt(this,xt)&&Tt(this,xt)!==t.relatedTarget&&this.open&&(this.open=!1))};Us=new WeakSet;Ul=function(t){var e,i,a,s,r;const{key:o,ctrlKey:l,altKey:c,metaKey:p}=t;l||c||p||this.keysUsed.includes(o)&&(t.preventDefault(),t.stopPropagation(),o==="Tab"?(t.shiftKey?(i=(e=this.previousElementSibling)==null?void 0:e.focus)==null||i.call(e):(s=(a=this.nextElementSibling)==null?void 0:a.focus)==null||s.call(a),this.blur()):o==="Escape"&&((r=Tt(this,Ci))==null||r.focus(),this.open=!1))};wt.shadowRootOptions={mode:"open"};wt.getTemplateHTML=op;wt.getSlotTemplateHTML=lp;f.customElements.get("media-chrome-dialog")||f.customElements.define("media-chrome-dialog",wt);var dp=wt,mn=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},Z=(t,e,i)=>(mn(t,e,"read from private field"),i?i.call(t):e.get(t)),ge=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},ot=(t,e,i,a)=>(mn(t,e,"write to private field"),e.set(t,i),i),Ne=(t,e,i)=>(mn(t,e,"access private method"),i),Ge,Qa,na,ra,Pe,La,oa,la,da,pn,$l,ca,$s,ua,Hs,Ra,fn,js,Hl,Fs,jl,Ws,Fl,Bs,Wl;function cp(t){return`
    <style>
      :host {
        --_focus-box-shadow: var(--media-focus-box-shadow, inset 0 0 0 2px rgb(27 127 204 / .9));
        --_media-range-padding: var(--media-range-padding, var(--media-control-padding, 10px));

        box-shadow: var(--_focus-visible-box-shadow, none);
        background: var(--media-control-background, var(--media-secondary-color, rgb(20 20 30 / .7)));
        height: calc(var(--media-control-height, 24px) + 2 * var(--_media-range-padding));
        display: inline-flex;
        align-items: center;
        
        vertical-align: middle;
        box-sizing: border-box;
        position: relative;
        width: 100px;
        transition: background .15s linear;
        cursor: var(--media-cursor, pointer);
        pointer-events: auto;
        touch-action: none; 
      }

      
      input[type=range]:focus {
        outline: 0;
      }
      input[type=range]:focus::-webkit-slider-runnable-track {
        outline: 0;
      }

      :host(:hover) {
        background: var(--media-control-hover-background, rgb(50 50 70 / .7));
      }

      #leftgap {
        padding-left: var(--media-range-padding-left, var(--_media-range-padding));
      }

      #rightgap {
        padding-right: var(--media-range-padding-right, var(--_media-range-padding));
      }

      #startpoint,
      #endpoint {
        position: absolute;
      }

      #endpoint {
        right: 0;
      }

      #container {
        
        width: var(--media-range-track-width, 100%);
        transform: translate(var(--media-range-track-translate-x, 0px), var(--media-range-track-translate-y, 0px));
        position: relative;
        height: 100%;
        display: flex;
        align-items: center;
        min-width: 40px;
      }

      #range {
        
        display: var(--media-time-range-hover-display, block);
        bottom: var(--media-time-range-hover-bottom, -7px);
        height: var(--media-time-range-hover-height, max(100% + 7px, 25px));
        width: 100%;
        position: absolute;
        cursor: var(--media-cursor, pointer);

        -webkit-appearance: none; 
        -webkit-tap-highlight-color: transparent;
        background: transparent; 
        margin: 0;
        z-index: 1;
      }

      @media (hover: hover) {
        #range {
          bottom: var(--media-time-range-hover-bottom, -5px);
          height: var(--media-time-range-hover-height, max(100% + 5px, 20px));
        }
      }

      
      
      #range::-webkit-slider-thumb {
        -webkit-appearance: none;
        background: transparent;
        width: .1px;
        height: .1px;
      }

      
      #range::-moz-range-thumb {
        background: transparent;
        border: transparent;
        width: .1px;
        height: .1px;
      }

      #appearance {
        height: var(--media-range-track-height, 4px);
        display: flex;
        flex-direction: column;
        justify-content: center;
        width: 100%;
        position: absolute;
        
        will-change: transform;
      }

      #track {
        background: var(--media-range-track-background, rgb(255 255 255 / .2));
        border-radius: var(--media-range-track-border-radius, 1px);
        border: var(--media-range-track-border, none);
        outline: var(--media-range-track-outline);
        outline-offset: var(--media-range-track-outline-offset);
        backdrop-filter: var(--media-range-track-backdrop-filter);
        -webkit-backdrop-filter: var(--media-range-track-backdrop-filter);
        box-shadow: var(--media-range-track-box-shadow, none);
        position: absolute;
        width: 100%;
        height: 100%;
        overflow: hidden;
      }

      #progress,
      #pointer {
        position: absolute;
        height: 100%;
        will-change: width;
      }

      #progress {
        background: var(--media-range-bar-color, var(--media-primary-color, rgb(238 238 238)));
        transition: var(--media-range-track-transition);
      }

      #pointer {
        background: var(--media-range-track-pointer-background);
        border-right: var(--media-range-track-pointer-border-right);
        transition: visibility .25s, opacity .25s;
        visibility: hidden;
        opacity: 0;
      }

      @media (hover: hover) {
        :host(:hover) #pointer {
          transition: visibility .5s, opacity .5s;
          visibility: visible;
          opacity: 1;
        }
      }

      #thumb,
      ::slotted([slot=thumb]) {
        width: var(--media-range-thumb-width, 10px);
        height: var(--media-range-thumb-height, 10px);
        transition: var(--media-range-thumb-transition);
        transform: var(--media-range-thumb-transform, none);
        opacity: var(--media-range-thumb-opacity, 1);
        translate: -50%;
        position: absolute;
        left: 0;
        cursor: var(--media-cursor, pointer);
      }

      #thumb {
        border-radius: var(--media-range-thumb-border-radius, 10px);
        background: var(--media-range-thumb-background, var(--media-primary-color, rgb(238 238 238)));
        box-shadow: var(--media-range-thumb-box-shadow, 1px 1px 1px transparent);
        border: var(--media-range-thumb-border, none);
      }

      :host([disabled]) #thumb {
        background-color: #777;
      }

      .segments #appearance {
        height: var(--media-range-segment-hover-height, 7px);
      }

      #track {
        clip-path: url(#segments-clipping);
      }

      #segments {
        --segments-gap: var(--media-range-segments-gap, 2px);
        position: absolute;
        width: 100%;
        height: 100%;
      }

      #segments-clipping {
        transform: translateX(calc(var(--segments-gap) / 2));
      }

      #segments-clipping:empty {
        display: none;
      }

      #segments-clipping rect {
        height: var(--media-range-track-height, 4px);
        y: calc((var(--media-range-segment-hover-height, 7px) - var(--media-range-track-height, 4px)) / 2);
        transition: var(--media-range-segment-transition, transform .1s ease-in-out);
        transform: var(--media-range-segment-transform, scaleY(1));
        transform-origin: center;
      }

      /* Visible label for accessibility - positioned off-screen but technically visible (Firefox requires visible labels) */
      #range-label {
        position: absolute;
        left: -10000px;
        background: var(--media-control-background, var(--media-secondary-color, rgb(20 20 30 / .7)));
        pointer-events: none;
      }
    </style>
    <div id="leftgap"></div>
    <div id="container">
      <div id="startpoint"></div>
      <div id="endpoint"></div>
      <div id="appearance">
        <div id="track" part="track">
          <div id="pointer"></div>
          <div id="progress" part="progress"></div>
        </div>
        <slot name="thumb">
          <div id="thumb" part="thumb"></div>
        </slot>
        <svg id="segments" aria-hidden="true"><clipPath id="segments-clipping"></clipPath></svg>
      </div>
        <input id="range" type="range" min="0" max="1" step="any" value="0">
        <label for="range" id="range-label"></label>

      ${this.getContainerTemplateHTML(t)}
    </div>
    <div id="rightgap"></div>
  `}function up(t){return""}class St extends f.HTMLElement{constructor(){if(super(),ge(this,pn),ge(this,ca),ge(this,ua),ge(this,Ra),ge(this,js),ge(this,Fs),ge(this,Ws),ge(this,Bs),ge(this,Ge,void 0),ge(this,Qa,void 0),ge(this,na,void 0),ge(this,ra,void 0),ge(this,Pe,{}),ge(this,La,[]),ge(this,oa,()=>{if(this.range.matches(":focus-visible")){const{style:e}=ue(this.shadowRoot,":host");e.setProperty("--_focus-visible-box-shadow","var(--_focus-box-shadow)")}}),ge(this,la,()=>{const{style:e}=ue(this.shadowRoot,":host");e.removeProperty("--_focus-visible-box-shadow")}),ge(this,da,()=>{const e=this.shadowRoot.querySelector("#segments-clipping");e&&e.parentNode.append(e)}),!this.shadowRoot){this.attachShadow(this.constructor.shadowRootOptions);const e=$e(this.attributes),i=this.constructor.getTemplateHTML(e);this.shadowRoot.setHTMLUnsafe?this.shadowRoot.setHTMLUnsafe(i):this.shadowRoot.innerHTML=i}this.container=this.shadowRoot.querySelector("#container"),ot(this,na,this.shadowRoot.querySelector("#startpoint")),ot(this,ra,this.shadowRoot.querySelector("#endpoint")),this.range=this.shadowRoot.querySelector("#range"),this.appearance=this.shadowRoot.querySelector("#appearance")}static get observedAttributes(){return["disabled","aria-disabled",z.MEDIA_CONTROLLER]}attributeChangedCallback(e,i,a){var s,r,o,l,c;e===z.MEDIA_CONTROLLER?(i&&((r=(s=Z(this,Ge))==null?void 0:s.unassociateElement)==null||r.call(s,this),ot(this,Ge,null)),a&&this.isConnected&&(ot(this,Ge,(o=this.getRootNode())==null?void 0:o.getElementById(a)),(c=(l=Z(this,Ge))==null?void 0:l.associateElement)==null||c.call(l,this))):(e==="disabled"||e==="aria-disabled"&&i!==a)&&(a==null?(this.range.removeAttribute(e),Ne(this,ca,$s).call(this)):(this.range.setAttribute(e,a),Ne(this,ua,Hs).call(this)))}connectedCallback(){var e,i,a;const{style:s}=ue(this.shadowRoot,":host");s.setProperty("display",`var(--media-control-display, var(--${this.localName}-display, inline-flex))`),Z(this,Pe).pointer=ue(this.shadowRoot,"#pointer"),Z(this,Pe).progress=ue(this.shadowRoot,"#progress"),Z(this,Pe).thumb=ue(this.shadowRoot,'#thumb, ::slotted([slot="thumb"])'),Z(this,Pe).activeSegment=ue(this.shadowRoot,"#segments-clipping rect:nth-child(0)");const r=this.getAttribute(z.MEDIA_CONTROLLER);r&&(ot(this,Ge,(e=this.getRootNode())==null?void 0:e.getElementById(r)),(a=(i=Z(this,Ge))==null?void 0:i.associateElement)==null||a.call(i,this)),this.updateBar(),this.shadowRoot.addEventListener("focusin",Z(this,oa)),this.shadowRoot.addEventListener("focusout",Z(this,la)),Ne(this,ca,$s).call(this),ol(this.container,Z(this,da))}disconnectedCallback(){var e,i;Ne(this,ua,Hs).call(this),(i=(e=Z(this,Ge))==null?void 0:e.unassociateElement)==null||i.call(e,this),ot(this,Ge,null),this.shadowRoot.removeEventListener("focusin",Z(this,oa)),this.shadowRoot.removeEventListener("focusout",Z(this,la)),ll(this.container,Z(this,da))}updatePointerBar(e){var i;(i=Z(this,Pe).pointer)==null||i.style.setProperty("width",`${this.getPointerRatio(e)*100}%`)}updateBar(){var e,i;const a=this.range.valueAsNumber*100;(e=Z(this,Pe).progress)==null||e.style.setProperty("width",`${a}%`),(i=Z(this,Pe).thumb)==null||i.style.setProperty("left",`${a}%`)}updateSegments(e){const i=this.shadowRoot.querySelector("#segments-clipping");if(i.textContent="",this.container.classList.toggle("segments",!!(e!=null&&e.length)),!(e!=null&&e.length))return;const a=[...new Set([+this.range.min,...e.flatMap(r=>[r.start,r.end]),+this.range.max])];ot(this,La,[...a]);const s=a.pop();for(const[r,o]of a.entries()){const[l,c]=[r===0,r===a.length-1],p=l?"calc(var(--segments-gap) / -1)":`${o*100}%`,E=`calc(${((c?s:a[r+1])-o)*100}%${l||c?"":" - var(--segments-gap)"})`,m=Ae.createElementNS("http://www.w3.org/2000/svg","rect"),v=ml(this.shadowRoot,`#segments-clipping rect:nth-child(${r+1})`);v.style.setProperty("x",p),v.style.setProperty("width",E),i.append(m)}}getPointerRatio(e){return Yh(e.clientX,e.clientY,Z(this,na).getBoundingClientRect(),Z(this,ra).getBoundingClientRect())}get dragging(){return this.hasAttribute("dragging")}handleEvent(e){switch(e.type){case"pointermove":Ne(this,Bs,Wl).call(this,e);break;case"input":this.updateBar();break;case"pointerenter":Ne(this,js,Hl).call(this,e);break;case"pointerdown":Ne(this,Ra,fn).call(this,e);break;case"pointerup":Ne(this,Fs,jl).call(this);break;case"pointerleave":Ne(this,Ws,Fl).call(this);break}}get keysUsed(){return["ArrowUp","ArrowRight","ArrowDown","ArrowLeft"]}}Ge=new WeakMap;Qa=new WeakMap;na=new WeakMap;ra=new WeakMap;Pe=new WeakMap;La=new WeakMap;oa=new WeakMap;la=new WeakMap;da=new WeakMap;pn=new WeakSet;$l=function(t){const e=Z(this,Pe).activeSegment;if(!e)return;const i=this.getPointerRatio(t),s=`#segments-clipping rect:nth-child(${Z(this,La).findIndex((r,o,l)=>{const c=l[o+1];return c!=null&&i>=r&&i<=c})+1})`;(e.selectorText!=s||!e.style.transform)&&(e.selectorText=s,e.style.setProperty("transform","var(--media-range-segment-hover-transform, scaleY(2))"))};ca=new WeakSet;$s=function(){this.hasAttribute("disabled")||!this.isConnected||(this.addEventListener("input",this),this.addEventListener("pointerdown",this),this.addEventListener("pointerenter",this))};ua=new WeakSet;Hs=function(){var t,e;this.removeEventListener("input",this),this.removeEventListener("pointerdown",this),this.removeEventListener("pointerenter",this),this.removeEventListener("pointerleave",this),(t=f.window)==null||t.removeEventListener("pointerup",this),(e=f.window)==null||e.removeEventListener("pointermove",this)};Ra=new WeakSet;fn=function(t){var e;ot(this,Qa,t.composedPath().includes(this.range)),(e=f.window)==null||e.addEventListener("pointerup",this,{once:!0})};js=new WeakSet;Hl=function(t){var e;t.pointerType!=="mouse"&&Ne(this,Ra,fn).call(this,t),this.addEventListener("pointerleave",this,{once:!0}),(e=f.window)==null||e.addEventListener("pointermove",this)};Fs=new WeakSet;jl=function(){var t;(t=f.window)==null||t.removeEventListener("pointerup",this),this.toggleAttribute("dragging",!1),this.range.disabled=this.hasAttribute("disabled")};Ws=new WeakSet;Fl=function(){var t,e;this.removeEventListener("pointerleave",this),(t=f.window)==null||t.removeEventListener("pointermove",this),this.toggleAttribute("dragging",!1),this.range.disabled=this.hasAttribute("disabled"),(e=Z(this,Pe).activeSegment)==null||e.style.removeProperty("transform")};Bs=new WeakSet;Wl=function(t){t.pointerType==="pen"&&t.buttons===0||(this.toggleAttribute("dragging",t.buttons===1||t.pointerType!=="mouse"),this.updatePointerBar(t),Ne(this,pn,$l).call(this,t),this.dragging&&(t.pointerType!=="mouse"||!Z(this,Qa))&&(this.range.disabled=!0,this.range.valueAsNumber=this.getPointerRatio(t),this.range.dispatchEvent(new Event("input",{bubbles:!0,composed:!0}))))};St.shadowRootOptions={mode:"open"};St.getTemplateHTML=cp;St.getContainerTemplateHTML=up;f.customElements.get("media-chrome-range")||f.customElements.define("media-chrome-range",St);var hp=St,Bl=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},Vi=(t,e,i)=>(Bl(t,e,"read from private field"),i?i.call(t):e.get(t)),mp=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},Gi=(t,e,i,a)=>(Bl(t,e,"write to private field"),e.set(t,i),i),Ke;function pp(t){return`
    <style>
      :host {
        
        box-sizing: border-box;
        display: var(--media-control-display, var(--media-control-bar-display, inline-flex));
        color: var(--media-text-color, var(--media-primary-color, rgb(238 238 238)));
        --media-loading-indicator-icon-height: 44px;
      }

      ::slotted(media-time-range),
      ::slotted(media-volume-range) {
        min-height: 100%;
      }

      ::slotted(media-time-range),
      ::slotted(media-clip-selector) {
        flex-grow: 1;
      }

      ::slotted([role="menu"]) {
        position: absolute;
      }
    </style>

    <slot></slot>
  `}let Xa=class extends f.HTMLElement{constructor(){if(super(),mp(this,Ke,void 0),!this.shadowRoot){this.attachShadow(this.constructor.shadowRootOptions);const e=$e(this.attributes);this.shadowRoot.innerHTML=this.constructor.getTemplateHTML(e)}}static get observedAttributes(){return[z.MEDIA_CONTROLLER]}attributeChangedCallback(e,i,a){var s,r,o,l,c;e===z.MEDIA_CONTROLLER&&(i&&((r=(s=Vi(this,Ke))==null?void 0:s.unassociateElement)==null||r.call(s,this),Gi(this,Ke,null)),a&&this.isConnected&&(Gi(this,Ke,(o=this.getRootNode())==null?void 0:o.getElementById(a)),(c=(l=Vi(this,Ke))==null?void 0:l.associateElement)==null||c.call(l,this)))}connectedCallback(){var e,i,a;const s=this.getAttribute(z.MEDIA_CONTROLLER);s&&(Gi(this,Ke,(e=this.getRootNode())==null?void 0:e.getElementById(s)),(a=(i=Vi(this,Ke))==null?void 0:i.associateElement)==null||a.call(i,this))}disconnectedCallback(){var e,i;(i=(e=Vi(this,Ke))==null?void 0:e.unassociateElement)==null||i.call(e,this),Gi(this,Ke,null)}};Ke=new WeakMap;Xa.shadowRootOptions={mode:"open"};Xa.getTemplateHTML=pp;f.customElements.get("media-control-bar")||f.customElements.define("media-control-bar",Xa);var fp=Xa,Vl=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},Ki=(t,e,i)=>(Vl(t,e,"read from private field"),i?i.call(t):e.get(t)),vp=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},zi=(t,e,i,a)=>(Vl(t,e,"write to private field"),e.set(t,i),i),ze;function gp(t,e={}){return`
    <style>
      :host {
        font: var(--media-font,
          var(--media-font-weight, normal)
          var(--media-font-size, 14px) /
          var(--media-text-content-height, var(--media-control-height, 24px))
          var(--media-font-family, helvetica neue, segoe ui, roboto, arial, sans-serif));
        color: var(--media-text-color, var(--media-primary-color, rgb(238 238 238)));
        background: var(--media-text-background, var(--media-control-background, var(--media-secondary-color, rgb(20 20 30 / .7))));
        padding: var(--media-control-padding, 10px);
        display: inline-flex;
        justify-content: center;
        align-items: center;
        vertical-align: middle;
        box-sizing: border-box;
        text-align: center;
        pointer-events: auto;
      }

      
      :host(:focus-visible) {
        box-shadow: inset 0 0 0 2px rgb(27 127 204 / .9);
        outline: 0;
      }

      
      :host(:where(:focus)) {
        box-shadow: none;
        outline: 0;
      }
    </style>

    ${this.getSlotTemplateHTML(t,e)}
  `}function Ep(t,e){return`
    <slot></slot>
  `}class it extends f.HTMLElement{constructor(){if(super(),vp(this,ze,void 0),!this.shadowRoot){this.attachShadow(this.constructor.shadowRootOptions);const e=$e(this.attributes);this.shadowRoot.innerHTML=this.constructor.getTemplateHTML(e)}}static get observedAttributes(){return[z.MEDIA_CONTROLLER]}attributeChangedCallback(e,i,a){var s,r,o,l,c;e===z.MEDIA_CONTROLLER&&(i&&((r=(s=Ki(this,ze))==null?void 0:s.unassociateElement)==null||r.call(s,this),zi(this,ze,null)),a&&this.isConnected&&(zi(this,ze,(o=this.getRootNode())==null?void 0:o.getElementById(a)),(c=(l=Ki(this,ze))==null?void 0:l.associateElement)==null||c.call(l,this)))}connectedCallback(){var e,i,a;const{style:s}=ue(this.shadowRoot,":host");s.setProperty("display",`var(--media-control-display, var(--${this.localName}-display, inline-flex))`);const r=this.getAttribute(z.MEDIA_CONTROLLER);r&&(zi(this,ze,(e=this.getRootNode())==null?void 0:e.getElementById(r)),(a=(i=Ki(this,ze))==null?void 0:i.associateElement)==null||a.call(i,this))}disconnectedCallback(){var e,i;(i=(e=Ki(this,ze))==null?void 0:e.unassociateElement)==null||i.call(e,this),zi(this,ze,null)}}ze=new WeakMap;it.shadowRootOptions={mode:"open"};it.getTemplateHTML=gp;it.getSlotTemplateHTML=Ep;f.customElements.get("media-text-display")||f.customElements.define("media-text-display",it);var bp=it,Gl=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},_r=(t,e,i)=>(Gl(t,e,"read from private field"),i?i.call(t):e.get(t)),_p=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},Ap=(t,e,i,a)=>(Gl(t,e,"write to private field"),e.set(t,i),i),gi;function yp(t,e){return`
    <slot>${mt(e.mediaDuration)}</slot>
  `}let vn=class extends it{constructor(){var e;super(),_p(this,gi,void 0),Ap(this,gi,this.shadowRoot.querySelector("slot")),_r(this,gi).textContent=mt((e=this.mediaDuration)!=null?e:0)}static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_DURATION]}attributeChangedCallback(e,i,a){e===d.MEDIA_DURATION&&(_r(this,gi).textContent=mt(+a)),super.attributeChangedCallback(e,i,a)}get mediaDuration(){return J(this,d.MEDIA_DURATION)}set mediaDuration(e){fe(this,d.MEDIA_DURATION,e)}};gi=new WeakMap;vn.getSlotTemplateHTML=yp;f.customElements.get("media-duration-display")||f.customElements.define("media-duration-display",vn);var Tp=vn;const xp={2:k("Network Error"),3:k("Decode Error"),4:k("Source Not Supported"),5:k("Encryption Error")},wp={2:k("A network error caused the media download to fail."),3:k("A media error caused playback to be aborted. The media could be corrupt or your browser does not support this format."),4:k("An unsupported error occurred. The server or network failed, or your browser does not support this format."),5:k("The media is encrypted and there are no keys to decrypt it.")},gn=t=>{var e,i;return t.code===1?null:{title:(e=xp[t.code])!=null?e:`Error ${t.code}`,message:(i=wp[t.code])!=null?i:t.message}};var Kl=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},Sp=(t,e,i)=>(Kl(t,e,"read from private field"),i?i.call(t):e.get(t)),Ip=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},kp=(t,e,i,a)=>(Kl(t,e,"write to private field"),e.set(t,i),i),ha;function Mp(t){return`
    <style>
      :host {
        background: rgb(20 20 30 / .8);
      }

      #content {
        display: block;
        padding: 1.2em 1.5em;
      }

      h3,
      p {
        margin-block: 0 .3em;
      }
    </style>
    <slot name="error-${t.mediaerrorcode}" id="content">
      ${zl({code:+t.mediaerrorcode,message:t.mediaerrormessage})}
    </slot>
  `}function Cp(t){return t.code&&gn(t)!==null}function zl(t){var e;const{title:i,message:a}=(e=gn(t))!=null?e:{};let s="";return i&&(s+=`<slot name="error-${t.code}-title"><h3>${i}</h3></slot>`),a&&(s+=`<slot name="error-${t.code}-message"><p>${a}</p></slot>`),s}const Ar=[d.MEDIA_ERROR_CODE,d.MEDIA_ERROR_MESSAGE];class Za extends wt{constructor(){super(...arguments),Ip(this,ha,null)}static get observedAttributes(){return[...super.observedAttributes,...Ar]}formatErrorMessage(e){return this.constructor.formatErrorMessage(e)}attributeChangedCallback(e,i,a){var s;if(super.attributeChangedCallback(e,i,a),!Ar.includes(e))return;const r=(s=this.mediaError)!=null?s:{code:this.mediaErrorCode,message:this.mediaErrorMessage};if(this.open=Cp(r),this.open&&(this.shadowRoot.querySelector("slot").name=`error-${this.mediaErrorCode}`,this.shadowRoot.querySelector("#content").innerHTML=this.formatErrorMessage(r),!this.hasAttribute("aria-label"))){const{title:o}=gn(r);o&&this.setAttribute("aria-label",o)}}get mediaError(){return Sp(this,ha)}set mediaError(e){kp(this,ha,e)}get mediaErrorCode(){return J(this,"mediaerrorcode")}set mediaErrorCode(e){fe(this,"mediaerrorcode",e)}get mediaErrorMessage(){return ee(this,"mediaerrormessage")}set mediaErrorMessage(e){te(this,"mediaerrormessage",e)}}ha=new WeakMap;Za.getSlotTemplateHTML=Mp;Za.formatErrorMessage=zl;f.customElements.get("media-error-dialog")||f.customElements.define("media-error-dialog",Za);var Lp=Za,Rp=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},st=(t,e,i)=>(Rp(t,e,"read from private field"),i?i.call(t):e.get(t)),yr=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},$t,Ht;function Dp(t){return`
    <style>
      :host {
        position: fixed;
        top: 0;
        left: 0;
        z-index: 9999;
        background: rgb(20 20 30 / .8);
        backdrop-filter: blur(10px);
      }

      #content {
        display: block;
        width: clamp(400px, 40vw, 700px);
        max-width: 90vw;
        text-align: left;
      }

      h2 {
        margin: 0 0 1.5rem 0;
        font-size: 1.5rem;
        font-weight: 500;
        text-align: center;
      }

      .shortcuts-table {
        width: 100%;
        border-collapse: collapse;
      }

      .shortcuts-table tr {
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      }

      .shortcuts-table tr:last-child {
        border-bottom: none;
      }

      .shortcuts-table td {
        padding: 0.75rem 0.5rem;
      }

      .shortcuts-table td:first-child {
        text-align: right;
        padding-right: 1rem;
        width: 40%;
        min-width: 120px;
      }

      .shortcuts-table td:last-child {
        padding-left: 1rem;
      }

      .key {
        display: inline-block;
        background: rgba(255, 255, 255, 0.15);
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 4px;
        padding: 0.25rem 0.5rem;
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
        font-weight: 500;
        min-width: 1.5rem;
        text-align: center;
        margin: 0 0.2rem;
      }

      .description {
        color: rgba(255, 255, 255, 0.9);
        font-size: 0.95rem;
      }

      .key-combo {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 0.3rem;
      }

      .key-separator {
        color: rgba(255, 255, 255, 0.5);
        font-size: 0.9rem;
      }
    </style>
    <slot id="content">
      ${Np()}
    </slot>
  `}function Np(){return`
    <h2>Keyboard Shortcuts</h2>
    <table class="shortcuts-table">${[{keys:["Space","k"],description:"Toggle Playback"},{keys:["m"],description:"Toggle mute"},{keys:["f"],description:"Toggle fullscreen"},{keys:["c"],description:"Toggle captions or subtitles, if available"},{keys:["p"],description:"Toggle Picture in Picture"},{keys:["←","j"],description:"Seek back 10s"},{keys:["→","l"],description:"Seek forward 10s"},{keys:["↑"],description:"Turn volume up"},{keys:["↓"],description:"Turn volume down"},{keys:["< (SHIFT+,)"],description:"Decrease playback rate"},{keys:["> (SHIFT+.)"],description:"Increase playback rate"}].map(({keys:i,description:a})=>`
      <tr>
        <td>
          <div class="key-combo">${i.map((r,o)=>o>0?`<span class="key-separator">or</span><span class="key">${r}</span>`:`<span class="key">${r}</span>`).join("")}</div>
        </td>
        <td class="description">${a}</td>
      </tr>
    `).join("")}</table>
  `}class En extends wt{constructor(){super(...arguments),yr(this,$t,e=>{var i;if(!this.open)return;const a=(i=this.shadowRoot)==null?void 0:i.querySelector("#content");if(!a)return;const s=e.composedPath(),r=s[0]===this||s.includes(this),o=s.includes(a);r&&!o&&(this.open=!1)}),yr(this,Ht,e=>{if(!this.open)return;const i=e.shiftKey&&(e.key==="/"||e.key==="?");(e.key==="Escape"||i)&&!e.ctrlKey&&!e.altKey&&!e.metaKey&&(this.open=!1,e.preventDefault(),e.stopPropagation())})}connectedCallback(){super.connectedCallback(),this.open&&(this.addEventListener("click",st(this,$t)),document.addEventListener("keydown",st(this,Ht)))}disconnectedCallback(){this.removeEventListener("click",st(this,$t)),document.removeEventListener("keydown",st(this,Ht))}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),e==="open"&&(this.open?(this.addEventListener("click",st(this,$t)),document.addEventListener("keydown",st(this,Ht))):(this.removeEventListener("click",st(this,$t)),document.removeEventListener("keydown",st(this,Ht))))}}$t=new WeakMap;Ht=new WeakMap;En.getSlotTemplateHTML=Dp;f.customElements.get("media-keyboard-shortcuts-dialog")||f.customElements.define("media-keyboard-shortcuts-dialog",En);var Pp=En,ql=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},Op=(t,e,i)=>(ql(t,e,"read from private field"),e.get(t)),Up=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},$p=(t,e,i,a)=>(ql(t,e,"write to private field"),e.set(t,i),i),ma;const Hp=`<svg aria-hidden="true" viewBox="0 0 26 24">
  <path d="M16 3v2.5h3.5V9H22V3h-6ZM4 9h2.5V5.5H10V3H4v6Zm15.5 9.5H16V21h6v-6h-2.5v3.5ZM6.5 15H4v6h6v-2.5H6.5V15Z"/>
</svg>`,jp=`<svg aria-hidden="true" viewBox="0 0 26 24">
  <path d="M18.5 6.5V3H16v6h6V6.5h-3.5ZM16 21h2.5v-3.5H22V15h-6v6ZM4 17.5h3.5V21H10v-6H4v2.5Zm3.5-11H4V9h6V3H7.5v3.5Z"/>
</svg>`;function Fp(t){return`
    <style>
      :host([${d.MEDIA_IS_FULLSCREEN}]) slot[name=icon] slot:not([name=exit]) {
        display: none !important;
      }

      
      :host(:not([${d.MEDIA_IS_FULLSCREEN}])) slot[name=icon] slot:not([name=enter]) {
        display: none !important;
      }

      :host([${d.MEDIA_IS_FULLSCREEN}]) slot[name=tooltip-enter],
      :host(:not([${d.MEDIA_IS_FULLSCREEN}])) slot[name=tooltip-exit] {
        display: none;
      }
    </style>

    <slot name="icon">
      <slot name="enter">${Hp}</slot>
      <slot name="exit">${jp}</slot>
    </slot>
  `}function Wp(){return`
    <slot name="tooltip-enter">${k("Enter fullscreen mode")}</slot>
    <slot name="tooltip-exit">${k("Exit fullscreen mode")}</slot>
  `}const Tr=t=>{const e=t.mediaIsFullscreen?k("exit fullscreen mode"):k("enter fullscreen mode");t.setAttribute("aria-label",e)};class Ja extends ve{constructor(){super(...arguments),Up(this,ma,null)}static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_IS_FULLSCREEN,d.MEDIA_FULLSCREEN_UNAVAILABLE]}connectedCallback(){super.connectedCallback(),Tr(this)}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),e===d.MEDIA_IS_FULLSCREEN&&Tr(this)}get mediaFullscreenUnavailable(){return ee(this,d.MEDIA_FULLSCREEN_UNAVAILABLE)}set mediaFullscreenUnavailable(e){te(this,d.MEDIA_FULLSCREEN_UNAVAILABLE,e)}get mediaIsFullscreen(){return j(this,d.MEDIA_IS_FULLSCREEN)}set mediaIsFullscreen(e){F(this,d.MEDIA_IS_FULLSCREEN,e)}handleClick(e){$p(this,ma,e);const i=Op(this,ma)instanceof PointerEvent,a=this.mediaIsFullscreen?new f.CustomEvent(w.MEDIA_EXIT_FULLSCREEN_REQUEST,{composed:!0,bubbles:!0}):new f.CustomEvent(w.MEDIA_ENTER_FULLSCREEN_REQUEST,{composed:!0,bubbles:!0,detail:i});this.dispatchEvent(a)}}ma=new WeakMap;Ja.getSlotTemplateHTML=Fp;Ja.getTooltipContentHTML=Wp;f.customElements.get("media-fullscreen-button")||f.customElements.define("media-fullscreen-button",Ja);var Bp=Ja;const{MEDIA_TIME_IS_LIVE:pa,MEDIA_PAUSED:xi}=d,{MEDIA_SEEK_TO_LIVE_REQUEST:Vp,MEDIA_PLAY_REQUEST:Gp}=w,Kp='<svg viewBox="0 0 6 12" aria-hidden="true"><circle cx="3" cy="6" r="2"></circle></svg>';function zp(t){return`
    <style>
      :host { --media-tooltip-display: none; }
      
      slot[name=indicator] > *,
      :host ::slotted([slot=indicator]) {
        
        min-width: auto;
        fill: var(--media-live-button-icon-color, rgb(140, 140, 140));
        color: var(--media-live-button-icon-color, rgb(140, 140, 140));
      }

      :host([${pa}]:not([${xi}])) slot[name=indicator] > *,
      :host([${pa}]:not([${xi}])) ::slotted([slot=indicator]) {
        fill: var(--media-live-button-indicator-color, rgb(255, 0, 0));
        color: var(--media-live-button-indicator-color, rgb(255, 0, 0));
      }

      :host([${pa}]:not([${xi}])) {
        cursor: var(--media-cursor, not-allowed);
      }

      slot[name=text]{
        text-transform: uppercase;
      }

    </style>

    <slot name="indicator">${Kp}</slot>
    
    <slot name="spacer">&nbsp;</slot><slot name="text">${k("live")}</slot>
  `}const xr=t=>{var e;const i=t.mediaPaused||!t.mediaTimeIsLive,a=k(i?"seek to live":"playing live");t.setAttribute("aria-label",a);const s=(e=t.shadowRoot)==null?void 0:e.querySelector('slot[name="text"]');s&&(s.textContent=k("live")),i?t.removeAttribute("aria-disabled"):t.setAttribute("aria-disabled","true")};class bn extends ve{static get observedAttributes(){return[...super.observedAttributes,pa,xi]}connectedCallback(){super.connectedCallback(),xr(this)}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),xr(this)}get mediaPaused(){return j(this,d.MEDIA_PAUSED)}set mediaPaused(e){F(this,d.MEDIA_PAUSED,e)}get mediaTimeIsLive(){return j(this,d.MEDIA_TIME_IS_LIVE)}set mediaTimeIsLive(e){F(this,d.MEDIA_TIME_IS_LIVE,e)}handleClick(){!this.mediaPaused&&this.mediaTimeIsLive||(this.dispatchEvent(new f.CustomEvent(Vp,{composed:!0,bubbles:!0})),this.hasAttribute(xi)&&this.dispatchEvent(new f.CustomEvent(Gp,{composed:!0,bubbles:!0})))}}bn.getSlotTemplateHTML=zp;f.customElements.get("media-live-button")||f.customElements.define("media-live-button",bn);var qp=bn,Yl=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},li=(t,e,i)=>(Yl(t,e,"read from private field"),i?i.call(t):e.get(t)),wr=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},di=(t,e,i,a)=>(Yl(t,e,"write to private field"),e.set(t,i),i),qe,fa;const qi={LOADING_DELAY:"loadingdelay",NO_AUTOHIDE:"noautohide"},Ql=500,Yp=`
<svg aria-hidden="true" viewBox="0 0 100 100">
  <path d="M73,50c0-12.7-10.3-23-23-23S27,37.3,27,50 M30.9,50c0-10.5,8.5-19.1,19.1-19.1S69.1,39.5,69.1,50">
    <animateTransform
       attributeName="transform"
       attributeType="XML"
       type="rotate"
       dur="1s"
       from="0 50 50"
       to="360 50 50"
       repeatCount="indefinite" />
  </path>
</svg>
`;function Qp(t){return`
    <style>
      :host {
        display: var(--media-control-display, var(--media-loading-indicator-display, inline-block));
        vertical-align: middle;
        box-sizing: border-box;
        --_loading-indicator-delay: var(--media-loading-indicator-transition-delay, ${Ql}ms);
      }

      #status {
        color: rgba(0,0,0,0);
        width: 0px;
        height: 0px;
      }

      :host slot[name=icon] > *,
      :host ::slotted([slot=icon]) {
        opacity: var(--media-loading-indicator-opacity, 0);
        transition: opacity 0.15s;
      }

      :host([${d.MEDIA_LOADING}]:not([${d.MEDIA_PAUSED}])) slot[name=icon] > *,
      :host([${d.MEDIA_LOADING}]:not([${d.MEDIA_PAUSED}])) ::slotted([slot=icon]) {
        opacity: var(--media-loading-indicator-opacity, 1);
        transition: opacity 0.15s var(--_loading-indicator-delay);
      }

      :host #status {
        visibility: var(--media-loading-indicator-opacity, hidden);
        transition: visibility 0.15s;
      }

      :host([${d.MEDIA_LOADING}]:not([${d.MEDIA_PAUSED}])) #status {
        visibility: var(--media-loading-indicator-opacity, visible);
        transition: visibility 0.15s var(--_loading-indicator-delay);
      }

      svg, img, ::slotted(svg), ::slotted(img) {
        width: var(--media-loading-indicator-icon-width);
        height: var(--media-loading-indicator-icon-height, 100px);
        fill: var(--media-icon-color, var(--media-primary-color, rgb(238 238 238)));
        vertical-align: middle;
      }
    </style>

    <slot name="icon">${Yp}</slot>
    <div id="status" role="status" aria-live="polite">${k("media loading")}</div>
  `}class es extends f.HTMLElement{constructor(){if(super(),wr(this,qe,void 0),wr(this,fa,Ql),!this.shadowRoot){this.attachShadow(this.constructor.shadowRootOptions);const e=$e(this.attributes);this.shadowRoot.innerHTML=this.constructor.getTemplateHTML(e)}}static get observedAttributes(){return[z.MEDIA_CONTROLLER,d.MEDIA_PAUSED,d.MEDIA_LOADING,qi.LOADING_DELAY]}attributeChangedCallback(e,i,a){var s,r,o,l,c;e===qi.LOADING_DELAY&&i!==a?this.loadingDelay=Number(a):e===z.MEDIA_CONTROLLER&&(i&&((r=(s=li(this,qe))==null?void 0:s.unassociateElement)==null||r.call(s,this),di(this,qe,null)),a&&this.isConnected&&(di(this,qe,(o=this.getRootNode())==null?void 0:o.getElementById(a)),(c=(l=li(this,qe))==null?void 0:l.associateElement)==null||c.call(l,this)))}connectedCallback(){var e,i,a;const s=this.getAttribute(z.MEDIA_CONTROLLER);s&&(di(this,qe,(e=this.getRootNode())==null?void 0:e.getElementById(s)),(a=(i=li(this,qe))==null?void 0:i.associateElement)==null||a.call(i,this))}disconnectedCallback(){var e,i;(i=(e=li(this,qe))==null?void 0:e.unassociateElement)==null||i.call(e,this),di(this,qe,null)}get loadingDelay(){return li(this,fa)}set loadingDelay(e){di(this,fa,e);const{style:i}=ue(this.shadowRoot,":host");i.setProperty("--_loading-indicator-delay",`var(--media-loading-indicator-transition-delay, ${e}ms)`)}get mediaPaused(){return j(this,d.MEDIA_PAUSED)}set mediaPaused(e){F(this,d.MEDIA_PAUSED,e)}get mediaLoading(){return j(this,d.MEDIA_LOADING)}set mediaLoading(e){F(this,d.MEDIA_LOADING,e)}get mediaController(){return ee(this,z.MEDIA_CONTROLLER)}set mediaController(e){te(this,z.MEDIA_CONTROLLER,e)}get noAutohide(){return j(this,qi.NO_AUTOHIDE)}set noAutohide(e){F(this,qi.NO_AUTOHIDE,e)}}qe=new WeakMap;fa=new WeakMap;es.shadowRootOptions={mode:"open"};es.getTemplateHTML=Qp;f.customElements.get("media-loading-indicator")||f.customElements.define("media-loading-indicator",es);var Xp=es;const Zp=`<svg aria-hidden="true" viewBox="0 0 24 24">
  <path d="M16.5 12A4.5 4.5 0 0 0 14 8v2.18l2.45 2.45a4.22 4.22 0 0 0 .05-.63Zm2.5 0a6.84 6.84 0 0 1-.54 2.64L20 16.15A8.8 8.8 0 0 0 21 12a9 9 0 0 0-7-8.77v2.06A7 7 0 0 1 19 12ZM4.27 3 3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25A6.92 6.92 0 0 1 14 18.7v2.06A9 9 0 0 0 17.69 19l2 2.05L21 19.73l-9-9L4.27 3ZM12 4 9.91 6.09 12 8.18V4Z"/>
</svg>`,Sr=`<svg aria-hidden="true" viewBox="0 0 24 24">
  <path d="M3 9v6h4l5 5V4L7 9H3Zm13.5 3A4.5 4.5 0 0 0 14 8v8a4.47 4.47 0 0 0 2.5-4Z"/>
</svg>`,Jp=`<svg aria-hidden="true" viewBox="0 0 24 24">
  <path d="M3 9v6h4l5 5V4L7 9H3Zm13.5 3A4.5 4.5 0 0 0 14 8v8a4.47 4.47 0 0 0 2.5-4ZM14 3.23v2.06a7 7 0 0 1 0 13.42v2.06a9 9 0 0 0 0-17.54Z"/>
</svg>`;function ef(t){return`
    <style>
      :host(:not([${d.MEDIA_VOLUME_LEVEL}])) slot[name=icon] slot:not([name=high]),
      :host([${d.MEDIA_VOLUME_LEVEL}=high]) slot[name=icon] slot:not([name=high]) {
        display: none !important;
      }

      :host([${d.MEDIA_VOLUME_LEVEL}=off]) slot[name=icon] slot:not([name=off]) {
        display: none !important;
      }

      :host([${d.MEDIA_VOLUME_LEVEL}=low]) slot[name=icon] slot:not([name=low]) {
        display: none !important;
      }

      :host([${d.MEDIA_VOLUME_LEVEL}=medium]) slot[name=icon] slot:not([name=medium]) {
        display: none !important;
      }

      :host(:not([${d.MEDIA_VOLUME_LEVEL}=off])) slot[name=tooltip-unmute],
      :host([${d.MEDIA_VOLUME_LEVEL}=off]) slot[name=tooltip-mute] {
        display: none;
      }
    </style>

    <slot name="icon">
      <slot name="off">${Zp}</slot>
      <slot name="low">${Sr}</slot>
      <slot name="medium">${Sr}</slot>
      <slot name="high">${Jp}</slot>
    </slot>
  `}function tf(){return`
    <slot name="tooltip-mute">${k("Mute")}</slot>
    <slot name="tooltip-unmute">${k("Unmute")}</slot>
  `}const Ir=t=>{const e=t.mediaVolumeLevel==="off",i=k(e?"unmute":"mute");t.setAttribute("aria-label",i)};let ts=class extends ve{static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_VOLUME_LEVEL]}connectedCallback(){super.connectedCallback(),Ir(this)}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),e===d.MEDIA_VOLUME_LEVEL&&Ir(this)}get mediaVolumeLevel(){return ee(this,d.MEDIA_VOLUME_LEVEL)}set mediaVolumeLevel(e){te(this,d.MEDIA_VOLUME_LEVEL,e)}handleClick(){const e=this.mediaVolumeLevel==="off"?w.MEDIA_UNMUTE_REQUEST:w.MEDIA_MUTE_REQUEST;this.dispatchEvent(new f.CustomEvent(e,{composed:!0,bubbles:!0}))}};ts.getSlotTemplateHTML=ef;ts.getTooltipContentHTML=tf;f.customElements.get("media-mute-button")||f.customElements.define("media-mute-button",ts);var af=ts;const kr=`<svg aria-hidden="true" viewBox="0 0 28 24">
  <path d="M24 3H4a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h20a1 1 0 0 0 1-1V4a1 1 0 0 0-1-1Zm-1 16H5V5h18v14Zm-3-8h-7v5h7v-5Z"/>
</svg>`;function sf(t){return`
    <style>
      :host([${d.MEDIA_IS_PIP}]) slot[name=icon] slot:not([name=exit]) {
        display: none !important;
      }

      :host(:not([${d.MEDIA_IS_PIP}])) slot[name=icon] slot:not([name=enter]) {
        display: none !important;
      }

      :host([${d.MEDIA_IS_PIP}]) slot[name=tooltip-enter],
      :host(:not([${d.MEDIA_IS_PIP}])) slot[name=tooltip-exit] {
        display: none;
      }
    </style>

    <slot name="icon">
      <slot name="enter">${kr}</slot>
      <slot name="exit">${kr}</slot>
    </slot>
  `}function nf(){return`
    <slot name="tooltip-enter">${k("Enter picture in picture mode")}</slot>
    <slot name="tooltip-exit">${k("Exit picture in picture mode")}</slot>
  `}const Mr=t=>{const e=t.mediaIsPip?k("exit picture in picture mode"):k("enter picture in picture mode");t.setAttribute("aria-label",e)};class is extends ve{static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_IS_PIP,d.MEDIA_PIP_UNAVAILABLE]}connectedCallback(){super.connectedCallback(),Mr(this)}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),e===d.MEDIA_IS_PIP&&Mr(this)}get mediaPipUnavailable(){return ee(this,d.MEDIA_PIP_UNAVAILABLE)}set mediaPipUnavailable(e){te(this,d.MEDIA_PIP_UNAVAILABLE,e)}get mediaIsPip(){return j(this,d.MEDIA_IS_PIP)}set mediaIsPip(e){F(this,d.MEDIA_IS_PIP,e)}handleClick(){const e=this.mediaIsPip?w.MEDIA_EXIT_PIP_REQUEST:w.MEDIA_ENTER_PIP_REQUEST;this.dispatchEvent(new f.CustomEvent(e,{composed:!0,bubbles:!0}))}}is.getSlotTemplateHTML=sf;is.getTooltipContentHTML=nf;f.customElements.get("media-pip-button")||f.customElements.define("media-pip-button",is);var rf=is,of=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},Ct=(t,e,i)=>(of(t,e,"read from private field"),i?i.call(t):e.get(t)),lf=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},lt;const fs={RATES:"rates"},df=[1,1.2,1.5,1.7,2],Ei=1;function cf(t){return`
    <style>
      :host {
        min-width: 5ch;
        padding: var(--media-button-padding, var(--media-control-padding, 10px 5px));
      }
    </style>
    <slot name="icon">${t.mediaplaybackrate||Ei}x</slot>
  `}function uf(){return k("Playback rate")}class as extends ve{constructor(){var e;super(),lf(this,lt,new bl(this,fs.RATES,{defaultValue:df})),this.container=this.shadowRoot.querySelector('slot[name="icon"]'),this.container.innerHTML=`${(e=this.mediaPlaybackRate)!=null?e:Ei}x`}static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_PLAYBACK_RATE,fs.RATES]}attributeChangedCallback(e,i,a){if(super.attributeChangedCallback(e,i,a),e===fs.RATES&&(Ct(this,lt).value=a),e===d.MEDIA_PLAYBACK_RATE){const s=a?+a:Number.NaN,r=Number.isNaN(s)?Ei:s;this.container.innerHTML=`${r}x`,this.setAttribute("aria-label",k("Playback rate {playbackRate}",{playbackRate:r}))}}get rates(){return Ct(this,lt)}set rates(e){e?Array.isArray(e)?Ct(this,lt).value=e.join(" "):typeof e=="string"&&(Ct(this,lt).value=e):Ct(this,lt).value=""}get mediaPlaybackRate(){return J(this,d.MEDIA_PLAYBACK_RATE,Ei)}set mediaPlaybackRate(e){fe(this,d.MEDIA_PLAYBACK_RATE,e)}handleClick(){var e,i;const a=Array.from(Ct(this,lt).values(),o=>+o).sort((o,l)=>o-l),s=(i=(e=a.find(o=>o>this.mediaPlaybackRate))!=null?e:a[0])!=null?i:Ei,r=new f.CustomEvent(w.MEDIA_PLAYBACK_RATE_REQUEST,{composed:!0,bubbles:!0,detail:s});this.dispatchEvent(r)}}lt=new WeakMap;as.getSlotTemplateHTML=cf;as.getTooltipContentHTML=uf;f.customElements.get("media-playback-rate-button")||f.customElements.define("media-playback-rate-button",as);var hf=as;const mf=`<svg aria-hidden="true" viewBox="0 0 24 24">
  <path d="m6 21 15-9L6 3v18Z"/>
</svg>`,pf=`<svg aria-hidden="true" viewBox="0 0 24 24">
  <path d="M6 20h4V4H6v16Zm8-16v16h4V4h-4Z"/>
</svg>`;function ff(t){return`
    <style>
      :host([${d.MEDIA_PAUSED}]) slot[name=pause],
      :host(:not([${d.MEDIA_PAUSED}])) slot[name=play] {
        display: none !important;
      }

      :host([${d.MEDIA_PAUSED}]) slot[name=tooltip-pause],
      :host(:not([${d.MEDIA_PAUSED}])) slot[name=tooltip-play] {
        display: none;
      }
    </style>

    <slot name="icon">
      <slot name="play">${mf}</slot>
      <slot name="pause">${pf}</slot>
    </slot>
  `}function vf(){return`
    <slot name="tooltip-play">${k("Play")}</slot>
    <slot name="tooltip-pause">${k("Pause")}</slot>
  `}const Cr=t=>{const e=t.mediaPaused?k("play"):k("pause");t.setAttribute("aria-label",e)};let ss=class extends ve{static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_PAUSED,d.MEDIA_ENDED]}connectedCallback(){super.connectedCallback(),Cr(this)}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),(e===d.MEDIA_PAUSED||e===d.MEDIA_LANG)&&Cr(this)}get mediaPaused(){return j(this,d.MEDIA_PAUSED)}set mediaPaused(e){F(this,d.MEDIA_PAUSED,e)}handleClick(){const e=this.mediaPaused?w.MEDIA_PLAY_REQUEST:w.MEDIA_PAUSE_REQUEST;this.dispatchEvent(new f.CustomEvent(e,{composed:!0,bubbles:!0}))}};ss.getSlotTemplateHTML=ff;ss.getTooltipContentHTML=vf;f.customElements.get("media-play-button")||f.customElements.define("media-play-button",ss);var gf=ss;const He={PLACEHOLDER_SRC:"placeholdersrc",SRC:"src"};function Ef(t){return`
    <style>
      :host {
        pointer-events: none;
        display: var(--media-poster-image-display, inline-block);
        box-sizing: border-box;
      }

      img {
        max-width: 100%;
        max-height: 100%;
        min-width: 100%;
        min-height: 100%;
        background-repeat: no-repeat;
        background-position: var(--media-poster-image-background-position, var(--media-object-position, center));
        background-size: var(--media-poster-image-background-size, var(--media-object-fit, contain));
        object-fit: var(--media-object-fit, contain);
        object-position: var(--media-object-position, center);
      }
    </style>

    <img part="poster img" aria-hidden="true" id="image"/>
  `}const bf=t=>{t.style.removeProperty("background-image")},_f=(t,e)=>{t.style["background-image"]=`url('${e}')`};class ns extends f.HTMLElement{static get observedAttributes(){return[He.PLACEHOLDER_SRC,He.SRC]}constructor(){if(super(),!this.shadowRoot){this.attachShadow(this.constructor.shadowRootOptions);const e=$e(this.attributes);this.shadowRoot.innerHTML=this.constructor.getTemplateHTML(e)}this.image=this.shadowRoot.querySelector("#image")}attributeChangedCallback(e,i,a){e===He.SRC&&(a==null?this.image.removeAttribute(He.SRC):this.image.setAttribute(He.SRC,a)),e===He.PLACEHOLDER_SRC&&(a==null?bf(this.image):_f(this.image,a))}get placeholderSrc(){return ee(this,He.PLACEHOLDER_SRC)}set placeholderSrc(e){te(this,He.SRC,e)}get src(){return ee(this,He.SRC)}set src(e){te(this,He.SRC,e)}}ns.shadowRootOptions={mode:"open"};ns.getTemplateHTML=Ef;f.customElements.get("media-poster-image")||f.customElements.define("media-poster-image",ns);var Af=ns,Xl=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},yf=(t,e,i)=>(Xl(t,e,"read from private field"),i?i.call(t):e.get(t)),Tf=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},xf=(t,e,i,a)=>(Xl(t,e,"write to private field"),e.set(t,i),i),va;class Zl extends it{constructor(){super(),Tf(this,va,void 0),xf(this,va,this.shadowRoot.querySelector("slot"))}static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_PREVIEW_CHAPTER,d.MEDIA_LANG]}attributeChangedCallback(e,i,a){if(super.attributeChangedCallback(e,i,a),(e===d.MEDIA_PREVIEW_CHAPTER||e===d.MEDIA_LANG)&&a!==i&&a!=null)if(yf(this,va).textContent=a,a!==""){const s=k("chapter: {chapterName}",{chapterName:a});this.setAttribute("aria-valuetext",s)}else this.removeAttribute("aria-valuetext")}get mediaPreviewChapter(){return ee(this,d.MEDIA_PREVIEW_CHAPTER)}set mediaPreviewChapter(e){te(this,d.MEDIA_PREVIEW_CHAPTER,e)}}va=new WeakMap;f.customElements.get("media-preview-chapter-display")||f.customElements.define("media-preview-chapter-display",Zl);var wf=Zl,Jl=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},Yi=(t,e,i)=>(Jl(t,e,"read from private field"),i?i.call(t):e.get(t)),Sf=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},Qi=(t,e,i,a)=>(Jl(t,e,"write to private field"),e.set(t,i),i),Ye;function If(t){return`
    <style>
      :host {
        box-sizing: border-box;
        display: var(--media-control-display, var(--media-preview-thumbnail-display, inline-block));
        overflow: hidden;
      }

      img {
        display: none;
        position: relative;
      }
    </style>
    <img crossorigin loading="eager" decoding="async">
  `}class rs extends f.HTMLElement{constructor(){if(super(),Sf(this,Ye,void 0),!this.shadowRoot){this.attachShadow(this.constructor.shadowRootOptions);const e=$e(this.attributes);this.shadowRoot.innerHTML=this.constructor.getTemplateHTML(e)}}static get observedAttributes(){return[z.MEDIA_CONTROLLER,d.MEDIA_PREVIEW_IMAGE,d.MEDIA_PREVIEW_COORDS]}connectedCallback(){var e,i,a;const s=this.getAttribute(z.MEDIA_CONTROLLER);s&&(Qi(this,Ye,(e=this.getRootNode())==null?void 0:e.getElementById(s)),(a=(i=Yi(this,Ye))==null?void 0:i.associateElement)==null||a.call(i,this))}disconnectedCallback(){var e,i;(i=(e=Yi(this,Ye))==null?void 0:e.unassociateElement)==null||i.call(e,this),Qi(this,Ye,null)}attributeChangedCallback(e,i,a){var s,r,o,l,c;[d.MEDIA_PREVIEW_IMAGE,d.MEDIA_PREVIEW_COORDS].includes(e)&&this.update(),e===z.MEDIA_CONTROLLER&&(i&&((r=(s=Yi(this,Ye))==null?void 0:s.unassociateElement)==null||r.call(s,this),Qi(this,Ye,null)),a&&this.isConnected&&(Qi(this,Ye,(o=this.getRootNode())==null?void 0:o.getElementById(a)),(c=(l=Yi(this,Ye))==null?void 0:l.associateElement)==null||c.call(l,this)))}get mediaPreviewImage(){return ee(this,d.MEDIA_PREVIEW_IMAGE)}set mediaPreviewImage(e){te(this,d.MEDIA_PREVIEW_IMAGE,e)}get mediaPreviewCoords(){const e=this.getAttribute(d.MEDIA_PREVIEW_COORDS);if(e)return e.split(/\s+/).map(i=>+i)}set mediaPreviewCoords(e){if(!e){this.removeAttribute(d.MEDIA_PREVIEW_COORDS);return}this.setAttribute(d.MEDIA_PREVIEW_COORDS,e.join(" "))}update(){const e=this.mediaPreviewCoords,i=this.mediaPreviewImage;if(!(e&&i))return;const[a,s,r,o]=e,l=i.split("#")[0],c=getComputedStyle(this),{maxWidth:p,maxHeight:u,minWidth:E,minHeight:m}=c,v=c.getPropertyValue("--media-preview-thumbnail-object-fit").trim()||"contain";let g,_;if(v==="fill"){const x=parseInt(p)/r,L=parseInt(u)/o,$=parseInt(E)/r,ie=parseInt(m)/o;g=x<1?x:Math.max(x,$),_=L<1?L:Math.max(L,ie)}else{const x=Math.min(parseInt(p)/r,parseInt(u)/o),L=Math.max(parseInt(E)/r,parseInt(m)/o),ie=x<1?x:L>1?L:1;g=ie,_=ie}const{style:A}=ue(this.shadowRoot,":host"),b=ue(this.shadowRoot,"img").style,T=this.shadowRoot.querySelector("img"),M=Math.min(g,_)<1?"min":"max";A.setProperty(`${M}-width`,"initial","important"),A.setProperty(`${M}-height`,"initial","important"),A.width=`${r*g}px`,A.height=`${o*_}px`;const I=()=>{b.width=`${this.imgWidth*g}px`,b.height=`${this.imgHeight*_}px`,b.display="block"};T.src!==l&&(T.onload=()=>{this.imgWidth=T.naturalWidth,this.imgHeight=T.naturalHeight,I(),T.onload=null},T.src=l,I()),I(),b.transform=`translate(-${a*g}px, -${s*_}px)`}}Ye=new WeakMap;rs.shadowRootOptions={mode:"open"};rs.getTemplateHTML=If;f.customElements.get("media-preview-thumbnail")||f.customElements.define("media-preview-thumbnail",rs);var Vs=rs,ed=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},Lr=(t,e,i)=>(ed(t,e,"read from private field"),i?i.call(t):e.get(t)),kf=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},Mf=(t,e,i,a)=>(ed(t,e,"write to private field"),e.set(t,i),i),bi;class td extends it{constructor(){super(),kf(this,bi,void 0),Mf(this,bi,this.shadowRoot.querySelector("slot")),Lr(this,bi).textContent=mt(0)}static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_PREVIEW_TIME]}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),e===d.MEDIA_PREVIEW_TIME&&a!=null&&(Lr(this,bi).textContent=mt(parseFloat(a)))}get mediaPreviewTime(){return J(this,d.MEDIA_PREVIEW_TIME)}set mediaPreviewTime(e){fe(this,d.MEDIA_PREVIEW_TIME,e)}}bi=new WeakMap;f.customElements.get("media-preview-time-display")||f.customElements.define("media-preview-time-display",td);var Cf=td;const Lt={SEEK_OFFSET:"seekoffset"},vs=30,Lf=t=>`
  <svg aria-hidden="true" viewBox="0 0 20 24">
    <defs>
      <style>.text{font-size:8px;font-family:Arial-BoldMT, Arial;font-weight:700;}</style>
    </defs>
    <text class="text value" transform="translate(2.18 19.87)">${t}</text>
    <path d="M10 6V3L4.37 7 10 10.94V8a5.54 5.54 0 0 1 1.9 10.48v2.12A7.5 7.5 0 0 0 10 6Z"/>
  </svg>`;function Rf(t,e){return`
    <slot name="icon">${Lf(e.seekOffset)}</slot>
  `}const Df=(t,e)=>{t.setAttribute("aria-label",k("seek back {seekOffset} seconds",{seekOffset:e}))};function Nf(){return k("Seek backward")}const Pf=0;class os extends ve{static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_CURRENT_TIME,Lt.SEEK_OFFSET]}connectedCallback(){super.connectedCallback(),this.seekOffset=J(this,Lt.SEEK_OFFSET,vs)}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),Df(this,this.seekOffset),e===Lt.SEEK_OFFSET&&(this.seekOffset=J(this,Lt.SEEK_OFFSET,vs))}get seekOffset(){return J(this,Lt.SEEK_OFFSET,vs)}set seekOffset(e){fe(this,Lt.SEEK_OFFSET,e),this.setAttribute("aria-label",k("seek back {seekOffset} seconds",{seekOffset:this.seekOffset})),dl(cl(this,"icon"),this.seekOffset)}get mediaCurrentTime(){return J(this,d.MEDIA_CURRENT_TIME,Pf)}set mediaCurrentTime(e){fe(this,d.MEDIA_CURRENT_TIME,e)}handleClick(){const e=Math.max(this.mediaCurrentTime-this.seekOffset,0),i=new f.CustomEvent(w.MEDIA_SEEK_REQUEST,{composed:!0,bubbles:!0,detail:e});this.dispatchEvent(i)}}os.getSlotTemplateHTML=Rf;os.getTooltipContentHTML=Nf;f.customElements.get("media-seek-backward-button")||f.customElements.define("media-seek-backward-button",os);var Of=os;const Rt={SEEK_OFFSET:"seekoffset"},gs=30,Uf=t=>`
  <svg aria-hidden="true" viewBox="0 0 20 24">
    <defs>
      <style>.text{font-size:8px;font-family:Arial-BoldMT, Arial;font-weight:700;}</style>
    </defs>
    <text class="text value" transform="translate(8.9 19.87)">${t}</text>
    <path d="M10 6V3l5.61 4L10 10.94V8a5.54 5.54 0 0 0-1.9 10.48v2.12A7.5 7.5 0 0 1 10 6Z"/>
  </svg>`;function $f(t,e){return`
    <slot name="icon">${Uf(e.seekOffset)}</slot>
  `}const Hf=(t,e)=>{t.setAttribute("aria-label",k("seek forward {seekOffset} seconds",{seekOffset:e}))};function jf(){return k("Seek forward")}const Ff=0;class ls extends ve{static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_CURRENT_TIME,Rt.SEEK_OFFSET]}connectedCallback(){super.connectedCallback(),this.seekOffset=J(this,Rt.SEEK_OFFSET,gs)}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),Hf(this,this.seekOffset),e===Rt.SEEK_OFFSET&&(this.seekOffset=J(this,Rt.SEEK_OFFSET,gs))}get seekOffset(){return J(this,Rt.SEEK_OFFSET,gs)}set seekOffset(e){fe(this,Rt.SEEK_OFFSET,e),this.setAttribute("aria-label",k("seek forward {seekOffset} seconds",{seekOffset:this.seekOffset})),dl(cl(this,"icon"),this.seekOffset)}get mediaCurrentTime(){return J(this,d.MEDIA_CURRENT_TIME,Ff)}set mediaCurrentTime(e){fe(this,d.MEDIA_CURRENT_TIME,e)}handleClick(){const e=this.mediaCurrentTime+this.seekOffset,i=new f.CustomEvent(w.MEDIA_SEEK_REQUEST,{composed:!0,bubbles:!0,detail:e});this.dispatchEvent(i)}}ls.getSlotTemplateHTML=$f;ls.getTooltipContentHTML=jf;f.customElements.get("media-seek-forward-button")||f.customElements.define("media-seek-forward-button",ls);var Wf=ls,_n=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},Oe=(t,e,i)=>(_n(t,e,"read from private field"),i?i.call(t):e.get(t)),vt=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},An=(t,e,i,a)=>(_n(t,e,"write to private field"),e.set(t,i),i),ct=(t,e,i)=>(_n(t,e,"access private method"),i),jt,Xe,ds,yn,id,Da,Tn,_i,ga,Ea,Gs;const dt={REMAINING:"remaining",SHOW_DURATION:"showduration",NO_TOGGLE:"notoggle"},Rr=[...Object.values(dt),d.MEDIA_CURRENT_TIME,d.MEDIA_DURATION,d.MEDIA_SEEKABLE],ad=["Enter"," "],Bf="&nbsp;/&nbsp;",Ks=(t,{timesSep:e=Bf}={})=>{var i,a;const s=(i=t.mediaCurrentTime)!=null?i:0,[,r]=(a=t.mediaSeekable)!=null?a:[];let o=0;Number.isFinite(t.mediaDuration)?o=t.mediaDuration:Number.isFinite(r)&&(o=r);const l=t.remaining?mt(0-(o-s)):mt(s);return t.showDuration?`${l}${e}${mt(o)}`:l},Vf=t=>{var e;const i=t.mediaCurrentTime,[,a]=(e=t.mediaSeekable)!=null?e:[];let s=null;if(Number.isFinite(t.mediaDuration)?s=t.mediaDuration:Number.isFinite(a)&&(s=a),i==null||s===null){t.setAttribute("aria-valuetext",k("video not loaded, unknown time."));return}const r=t.remaining?yi(0-(s-i)):yi(i);if(!t.showDuration){t.setAttribute("aria-valuetext",r);return}const o=yi(s),l=k("{currentTime} of {totalTime}",{currentTime:r,totalTime:o});t.setAttribute("aria-valuetext",l)};function Gf(t,e){return`
    <slot>${Ks(e)}</slot>
  `}const Kf=t=>{t.setAttribute("aria-label",k("playback time"))};let xn=class extends it{constructor(){super(),vt(this,yn),vt(this,Da),vt(this,_i),vt(this,Ea),vt(this,jt,void 0),vt(this,Xe,null),vt(this,ds,e=>{const{metaKey:i,altKey:a,key:s}=e;if(i||a||!ad.includes(s)){this.removeEventListener("keyup",Oe(this,Xe));return}this.addEventListener("keyup",Oe(this,Xe))}),An(this,jt,this.shadowRoot.querySelector("slot")),Oe(this,jt).innerHTML=`${Ks(this)}`}static get observedAttributes(){return[...super.observedAttributes,...Rr,"disabled"]}connectedCallback(){const{style:e}=ue(this.shadowRoot,":host(:hover:not([notoggle]))");e.setProperty("cursor","var(--media-cursor, pointer)"),e.setProperty("background","var(--media-control-hover-background, rgba(50 50 70 / .7))"),this.setAttribute("aria-label",k("playback time")),ct(this,_i,ga).call(this),super.connectedCallback()}toggleTimeDisplay(){this.noToggle||(this.hasAttribute("remaining")?this.removeAttribute("remaining"):this.setAttribute("remaining",""))}disconnectedCallback(){this.disable(),ct(this,Da,Tn).call(this),super.disconnectedCallback()}attributeChangedCallback(e,i,a){Kf(this),Rr.includes(e)?this.update():e==="disabled"&&a!==i?a==null?ct(this,_i,ga).call(this):ct(this,Ea,Gs).call(this):e===dt.NO_TOGGLE&&a!==i&&(this.noToggle?ct(this,Ea,Gs).call(this):ct(this,_i,ga).call(this)),super.attributeChangedCallback(e,i,a)}enable(){this.noToggle||(this.tabIndex=0)}disable(){this.tabIndex=-1}get remaining(){return j(this,dt.REMAINING)}set remaining(e){F(this,dt.REMAINING,e)}get showDuration(){return j(this,dt.SHOW_DURATION)}set showDuration(e){F(this,dt.SHOW_DURATION,e)}get noToggle(){return j(this,dt.NO_TOGGLE)}set noToggle(e){F(this,dt.NO_TOGGLE,e)}get mediaDuration(){return J(this,d.MEDIA_DURATION)}set mediaDuration(e){fe(this,d.MEDIA_DURATION,e)}get mediaCurrentTime(){return J(this,d.MEDIA_CURRENT_TIME)}set mediaCurrentTime(e){fe(this,d.MEDIA_CURRENT_TIME,e)}get mediaSeekable(){const e=this.getAttribute(d.MEDIA_SEEKABLE);if(e)return e.split(":").map(i=>+i)}set mediaSeekable(e){if(e==null){this.removeAttribute(d.MEDIA_SEEKABLE);return}this.setAttribute(d.MEDIA_SEEKABLE,e.join(":"))}update(){const e=Ks(this);Vf(this),e!==Oe(this,jt).innerHTML&&(Oe(this,jt).innerHTML=e)}};jt=new WeakMap;Xe=new WeakMap;ds=new WeakMap;yn=new WeakSet;id=function(){Oe(this,Xe)||(An(this,Xe,t=>{const{key:e}=t;if(!ad.includes(e)){this.removeEventListener("keyup",Oe(this,Xe));return}this.toggleTimeDisplay()}),this.addEventListener("keydown",Oe(this,ds)),this.addEventListener("click",this.toggleTimeDisplay))};Da=new WeakSet;Tn=function(){Oe(this,Xe)&&(this.removeEventListener("keyup",Oe(this,Xe)),this.removeEventListener("keydown",Oe(this,ds)),this.removeEventListener("click",this.toggleTimeDisplay),An(this,Xe,null))};_i=new WeakSet;ga=function(){!this.noToggle&&!this.hasAttribute("disabled")&&(this.setAttribute("role","button"),this.enable(),ct(this,yn,id).call(this))};Ea=new WeakSet;Gs=function(){this.removeAttribute("role"),this.disable(),ct(this,Da,Tn).call(this)};xn.getSlotTemplateHTML=Gf;f.customElements.get("media-time-display")||f.customElements.define("media-time-display",xn);var zf=xn,sd=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},me=(t,e,i)=>(sd(t,e,"read from private field"),e.get(t)),je=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},Se=(t,e,i,a)=>(sd(t,e,"write to private field"),e.set(t,i),i),qf=(t,e,i,a)=>({set _(s){Se(t,e,s)},get _(){return me(t,e)}}),Ft,ba,Wt,Ai,_a,Aa,ya,Bt,Et,Ta;class Yf{constructor(e,i,a){je(this,Ft,void 0),je(this,ba,void 0),je(this,Wt,void 0),je(this,Ai,void 0),je(this,_a,void 0),je(this,Aa,void 0),je(this,ya,void 0),je(this,Bt,void 0),je(this,Et,0),je(this,Ta,(s=performance.now())=>{Se(this,Et,requestAnimationFrame(me(this,Ta))),Se(this,Ai,performance.now()-me(this,Wt));const r=1e3/this.fps;if(me(this,Ai)>r){Se(this,Wt,s-me(this,Ai)%r);const o=1e3/((s-me(this,ba))/++qf(this,_a)._),l=(s-me(this,Aa))/1e3/this.duration;let c=me(this,ya)+l*this.playbackRate;c-me(this,Ft).valueAsNumber>0?Se(this,Bt,this.playbackRate/this.duration/o):(Se(this,Bt,.995*me(this,Bt)),c=me(this,Ft).valueAsNumber+me(this,Bt)),this.callback(c)}}),Se(this,Ft,e),this.callback=i,this.fps=a}start(){me(this,Et)===0&&(Se(this,Wt,performance.now()),Se(this,ba,me(this,Wt)),Se(this,_a,0),me(this,Ta).call(this))}stop(){me(this,Et)!==0&&(cancelAnimationFrame(me(this,Et)),Se(this,Et,0))}update({start:e,duration:i,playbackRate:a}){const s=e-me(this,Ft).valueAsNumber,r=Math.abs(i-this.duration);(s>0||s<-.03||r>=.5)&&this.callback(e),Se(this,ya,e),Se(this,Aa,performance.now()),this.duration=i,this.playbackRate=a}}Ft=new WeakMap;ba=new WeakMap;Wt=new WeakMap;Ai=new WeakMap;_a=new WeakMap;Aa=new WeakMap;ya=new WeakMap;Bt=new WeakMap;Et=new WeakMap;Ta=new WeakMap;var wn=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},Q=(t,e,i)=>(wn(t,e,"read from private field"),i?i.call(t):e.get(t)),ce=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},Ce=(t,e,i,a)=>(wn(t,e,"write to private field"),e.set(t,i),i),Le=(t,e,i)=>(wn(t,e,"access private method"),i),Vt,bt,Na,wi,Pa,xa,Li,Ri,Gt,Kt,zt,zs,nd,qs,Oa,Sn,Ua,In,$a,kn,Ys,rd,Di,Ha,Qs,od;const Qf=t=>{const e=t.range,i=yi(+ld(t)),a=yi(+t.mediaSeekableEnd),s=i&&a?k("{currentTime} of {totalTime}",{currentTime:i,totalTime:a}):k("video not loaded, unknown time.");e.setAttribute("aria-valuetext",s)};function Xf(t){return`
    <style>
      :host {
        --media-box-border-radius: 4px;
        --media-box-padding-left: 10px;
        --media-box-padding-right: 10px;
        --media-preview-border-radius: var(--media-box-border-radius);
        --media-box-arrow-offset: var(--media-box-border-radius);
        --_control-background: var(--media-control-background, var(--media-secondary-color, rgb(20 20 30 / .7)));
        --_preview-background: var(--media-preview-background, var(--_control-background));

        
        contain: layout;
      }

      #buffered {
        background: var(--media-time-range-buffered-color, rgb(255 255 255 / .4));
        position: absolute;
        height: 100%;
        will-change: width;
      }

      #preview-rail,
      #current-rail {
        width: 100%;
        position: absolute;
        left: 0;
        bottom: 100%;
        pointer-events: none;
        will-change: transform;
      }

      [part~="box"] {
        width: min-content;
        
        position: absolute;
        bottom: 100%;
        flex-direction: column;
        align-items: center;
        transform: translateX(-50%);
      }

      [part~="current-box"] {
        display: var(--media-current-box-display, var(--media-box-display, flex));
        margin: var(--media-current-box-margin, var(--media-box-margin, 0 0 5px));
        visibility: hidden;
      }

      [part~="preview-box"] {
        display: var(--media-preview-box-display, var(--media-box-display, flex));
        margin: var(--media-preview-box-margin, var(--media-box-margin, 0 0 5px));
        transition-property: var(--media-preview-transition-property, visibility, opacity);
        transition-duration: var(--media-preview-transition-duration-out, .25s);
        transition-delay: var(--media-preview-transition-delay-out, 0s);
        visibility: hidden;
        opacity: 0;
      }

      :host(:is([${d.MEDIA_PREVIEW_IMAGE}], [${d.MEDIA_PREVIEW_TIME}])[dragging]) [part~="preview-box"] {
        transition-duration: var(--media-preview-transition-duration-in, .5s);
        transition-delay: var(--media-preview-transition-delay-in, .25s);
        visibility: visible;
        opacity: 1;
      }

      @media (hover: hover) {
        :host(:is([${d.MEDIA_PREVIEW_IMAGE}], [${d.MEDIA_PREVIEW_TIME}]):hover) [part~="preview-box"] {
          transition-duration: var(--media-preview-transition-duration-in, .5s);
          transition-delay: var(--media-preview-transition-delay-in, .25s);
          visibility: visible;
          opacity: 1;
        }
      }

      media-preview-thumbnail,
      ::slotted(media-preview-thumbnail) {
        visibility: hidden;
        
        transition: visibility 0s .25s;
        transition-delay: calc(var(--media-preview-transition-delay-out, 0s) + var(--media-preview-transition-duration-out, .25s));
        background: var(--media-preview-thumbnail-background, var(--_preview-background));
        box-shadow: var(--media-preview-thumbnail-box-shadow, 0 0 4px rgb(0 0 0 / .2));
        max-width: var(--media-preview-thumbnail-max-width, 180px);
        max-height: var(--media-preview-thumbnail-max-height, 160px);
        min-width: var(--media-preview-thumbnail-min-width, 120px);
        min-height: var(--media-preview-thumbnail-min-height, 80px);
        border: var(--media-preview-thumbnail-border);
        border-radius: var(--media-preview-thumbnail-border-radius,
          var(--media-preview-border-radius) var(--media-preview-border-radius) 0 0);
      }

      :host([${d.MEDIA_PREVIEW_IMAGE}][dragging]) media-preview-thumbnail,
      :host([${d.MEDIA_PREVIEW_IMAGE}][dragging]) ::slotted(media-preview-thumbnail) {
        transition-delay: var(--media-preview-transition-delay-in, .25s);
        visibility: visible;
      }

      @media (hover: hover) {
        :host([${d.MEDIA_PREVIEW_IMAGE}]:hover) media-preview-thumbnail,
        :host([${d.MEDIA_PREVIEW_IMAGE}]:hover) ::slotted(media-preview-thumbnail) {
          transition-delay: var(--media-preview-transition-delay-in, .25s);
          visibility: visible;
        }

        :host([${d.MEDIA_PREVIEW_TIME}]:hover) {
          --media-time-range-hover-display: block;
        }
      }

      media-preview-chapter-display,
      ::slotted(media-preview-chapter-display) {
        font-size: var(--media-font-size, 13px);
        line-height: 17px;
        min-width: 0;
        visibility: hidden;
        
        transition: min-width 0s, border-radius 0s, margin 0s, padding 0s, visibility 0s;
        transition-delay: calc(var(--media-preview-transition-delay-out, 0s) + var(--media-preview-transition-duration-out, .25s));
        background: var(--media-preview-chapter-background, var(--_preview-background));
        border-radius: var(--media-preview-chapter-border-radius,
          var(--media-preview-border-radius) var(--media-preview-border-radius)
          var(--media-preview-border-radius) var(--media-preview-border-radius));
        padding: var(--media-preview-chapter-padding, 3.5px 9px);
        margin: var(--media-preview-chapter-margin, 0 0 5px);
        text-shadow: var(--media-preview-chapter-text-shadow, 0 0 4px rgb(0 0 0 / .75));
      }

      :host([${d.MEDIA_PREVIEW_IMAGE}]) media-preview-chapter-display,
      :host([${d.MEDIA_PREVIEW_IMAGE}]) ::slotted(media-preview-chapter-display) {
        transition-delay: var(--media-preview-transition-delay-in, .25s);
        border-radius: var(--media-preview-chapter-border-radius, 0);
        padding: var(--media-preview-chapter-padding, 3.5px 9px 0);
        margin: var(--media-preview-chapter-margin, 0);
        min-width: 100%;
      }

      media-preview-chapter-display[${d.MEDIA_PREVIEW_CHAPTER}],
      ::slotted(media-preview-chapter-display[${d.MEDIA_PREVIEW_CHAPTER}]) {
        visibility: visible;
      }

      media-preview-chapter-display:not([aria-valuetext]),
      ::slotted(media-preview-chapter-display:not([aria-valuetext])) {
        display: none;
      }

      media-preview-time-display,
      ::slotted(media-preview-time-display),
      media-time-display,
      ::slotted(media-time-display) {
        font-size: var(--media-font-size, 13px);
        line-height: 17px;
        min-width: 0;
        
        transition: min-width 0s, border-radius 0s;
        transition-delay: calc(var(--media-preview-transition-delay-out, 0s) + var(--media-preview-transition-duration-out, .25s));
        background: var(--media-preview-time-background, var(--_preview-background));
        border-radius: var(--media-preview-time-border-radius,
          var(--media-preview-border-radius) var(--media-preview-border-radius)
          var(--media-preview-border-radius) var(--media-preview-border-radius));
        padding: var(--media-preview-time-padding, 3.5px 9px);
        margin: var(--media-preview-time-margin, 0);
        text-shadow: var(--media-preview-time-text-shadow, 0 0 4px rgb(0 0 0 / .75));
        transform: translateX(min(
          max(calc(50% - var(--_box-width) / 2),
          calc(var(--_box-shift, 0))),
          calc(var(--_box-width) / 2 - 50%)
        ));
      }

      :host([${d.MEDIA_PREVIEW_IMAGE}]) media-preview-time-display,
      :host([${d.MEDIA_PREVIEW_IMAGE}]) ::slotted(media-preview-time-display) {
        transition-delay: var(--media-preview-transition-delay-in, .25s);
        border-radius: var(--media-preview-time-border-radius,
          0 0 var(--media-preview-border-radius) var(--media-preview-border-radius));
        min-width: 100%;
      }

      :host([${d.MEDIA_PREVIEW_TIME}]:hover) {
        --media-time-range-hover-display: block;
      }

      [part~="arrow"],
      ::slotted([part~="arrow"]) {
        display: var(--media-box-arrow-display, inline-block);
        transform: translateX(min(
          max(calc(50% - var(--_box-width) / 2 + var(--media-box-arrow-offset)),
          calc(var(--_box-shift, 0))),
          calc(var(--_box-width) / 2 - 50% - var(--media-box-arrow-offset))
        ));
        
        border-color: transparent;
        border-top-color: var(--media-box-arrow-background, var(--_control-background));
        border-width: var(--media-box-arrow-border-width,
          var(--media-box-arrow-height, 5px) var(--media-box-arrow-width, 6px) 0);
        border-style: solid;
        justify-content: center;
        height: 0;
      }
    </style>
    <div id="preview-rail">
      <slot name="preview" part="box preview-box">
        <media-preview-thumbnail>
          <template shadowrootmode="${Vs.shadowRootOptions.mode}">
            ${Vs.getTemplateHTML({})}
          </template>
        </media-preview-thumbnail>
        <media-preview-chapter-display></media-preview-chapter-display>
        <media-preview-time-display></media-preview-time-display>
        <slot name="preview-arrow"><div part="arrow"></div></slot>
      </slot>
    </div>
    <div id="current-rail">
      <slot name="current" part="box current-box">
        
      </slot>
    </div>
  `}const Xi=(t,e=t.mediaCurrentTime)=>{const i=Number.isFinite(t.mediaSeekableStart)?t.mediaSeekableStart:0,a=Number.isFinite(t.mediaDuration)?t.mediaDuration:t.mediaSeekableEnd;if(Number.isNaN(a))return 0;const s=(e-i)/(a-i);return Math.max(0,Math.min(s,1))},ld=(t,e=t.range.valueAsNumber)=>{const i=Number.isFinite(t.mediaSeekableStart)?t.mediaSeekableStart:0,a=Number.isFinite(t.mediaDuration)?t.mediaDuration:t.mediaSeekableEnd;return Number.isNaN(a)?0:e*(a-i)+i};let cs=class extends St{constructor(){super(),ce(this,zs),ce(this,Oa),ce(this,Ua),ce(this,$a),ce(this,Ys),ce(this,Di),ce(this,Qs),ce(this,Vt,null),ce(this,bt,void 0),ce(this,Na,void 0),ce(this,wi,void 0),ce(this,Pa,void 0),ce(this,xa,void 0),ce(this,Li,void 0),ce(this,Ri,void 0),ce(this,Gt,void 0),ce(this,Kt,void 0),ce(this,zt,()=>{Le(this,zs,nd).call(this)?Q(this,bt).start():Q(this,bt).stop()}),ce(this,qs,a=>{this.dragging||(an(a)&&(this.range.valueAsNumber=a),Q(this,Kt)||this.updateBar())}),this.shadowRoot.querySelector("#track").insertAdjacentHTML("afterbegin",'<div id="buffered" part="buffered"></div>'),Ce(this,Na,this.shadowRoot.querySelectorAll('[part~="box"]')),Ce(this,Pa,this.shadowRoot.querySelector('[part~="preview-box"]')),Ce(this,xa,this.shadowRoot.querySelector('[part~="current-box"]'));const i=getComputedStyle(this);Ce(this,Li,parseInt(i.getPropertyValue("--media-box-padding-left"))),Ce(this,Ri,parseInt(i.getPropertyValue("--media-box-padding-right"))),Ce(this,bt,new Yf(this.range,Q(this,qs),60))}static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_PAUSED,d.MEDIA_DURATION,d.MEDIA_SEEKABLE,d.MEDIA_CURRENT_TIME,d.MEDIA_PREVIEW_IMAGE,d.MEDIA_PREVIEW_TIME,d.MEDIA_PREVIEW_CHAPTER,d.MEDIA_BUFFERED,d.MEDIA_PLAYBACK_RATE,d.MEDIA_LOADING,d.MEDIA_ENDED]}connectedCallback(){var e;super.connectedCallback(),this.range.setAttribute("aria-label",k("seek")),Q(this,zt).call(this),Ce(this,Vt,this.getRootNode()),(e=Q(this,Vt))==null||e.addEventListener("transitionstart",this)}disconnectedCallback(){var e;super.disconnectedCallback(),Q(this,zt).call(this),(e=Q(this,Vt))==null||e.removeEventListener("transitionstart",this),Ce(this,Vt,null)}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),i!=a&&(e===d.MEDIA_CURRENT_TIME||e===d.MEDIA_PAUSED||e===d.MEDIA_ENDED||e===d.MEDIA_LOADING||e===d.MEDIA_DURATION||e===d.MEDIA_SEEKABLE?(Q(this,bt).update({start:Xi(this),duration:this.mediaSeekableEnd-this.mediaSeekableStart,playbackRate:this.mediaPlaybackRate}),Q(this,zt).call(this),Qf(this)):e===d.MEDIA_BUFFERED&&this.updateBufferedBar(),(e===d.MEDIA_DURATION||e===d.MEDIA_SEEKABLE)&&(this.mediaChaptersCues=Q(this,Gt),this.updateBar()))}get mediaChaptersCues(){return Q(this,Gt)}set mediaChaptersCues(e){var i;Ce(this,Gt,e),this.updateSegments((i=Q(this,Gt))==null?void 0:i.map(a=>({start:Xi(this,a.startTime),end:Xi(this,a.endTime)})))}get mediaPaused(){return j(this,d.MEDIA_PAUSED)}set mediaPaused(e){F(this,d.MEDIA_PAUSED,e)}get mediaLoading(){return j(this,d.MEDIA_LOADING)}set mediaLoading(e){F(this,d.MEDIA_LOADING,e)}get mediaDuration(){return J(this,d.MEDIA_DURATION)}set mediaDuration(e){fe(this,d.MEDIA_DURATION,e)}get mediaCurrentTime(){return J(this,d.MEDIA_CURRENT_TIME)}set mediaCurrentTime(e){fe(this,d.MEDIA_CURRENT_TIME,e)}get mediaPlaybackRate(){return J(this,d.MEDIA_PLAYBACK_RATE,1)}set mediaPlaybackRate(e){fe(this,d.MEDIA_PLAYBACK_RATE,e)}get mediaBuffered(){const e=this.getAttribute(d.MEDIA_BUFFERED);return e?e.split(" ").map(i=>i.split(":").map(a=>+a)):[]}set mediaBuffered(e){if(!e){this.removeAttribute(d.MEDIA_BUFFERED);return}const i=e.map(a=>a.join(":")).join(" ");this.setAttribute(d.MEDIA_BUFFERED,i)}get mediaSeekable(){const e=this.getAttribute(d.MEDIA_SEEKABLE);if(e)return e.split(":").map(i=>+i)}set mediaSeekable(e){if(e==null){this.removeAttribute(d.MEDIA_SEEKABLE);return}this.setAttribute(d.MEDIA_SEEKABLE,e.join(":"))}get mediaSeekableEnd(){var e;const[,i=this.mediaDuration]=(e=this.mediaSeekable)!=null?e:[];return i}get mediaSeekableStart(){var e;const[i=0]=(e=this.mediaSeekable)!=null?e:[];return i}get mediaPreviewImage(){return ee(this,d.MEDIA_PREVIEW_IMAGE)}set mediaPreviewImage(e){te(this,d.MEDIA_PREVIEW_IMAGE,e)}get mediaPreviewTime(){return J(this,d.MEDIA_PREVIEW_TIME)}set mediaPreviewTime(e){fe(this,d.MEDIA_PREVIEW_TIME,e)}get mediaEnded(){return j(this,d.MEDIA_ENDED)}set mediaEnded(e){F(this,d.MEDIA_ENDED,e)}updateBar(){super.updateBar(),this.updateBufferedBar(),this.updateCurrentBox()}updateBufferedBar(){var e;const i=this.mediaBuffered;if(!i.length)return;let a;if(this.mediaEnded)a=1;else{const r=this.mediaCurrentTime,[,o=this.mediaSeekableStart]=(e=i.find(([l,c])=>l<=r&&r<=c))!=null?e:[];a=Xi(this,o)}const{style:s}=ue(this.shadowRoot,"#buffered");s.setProperty("width",`${a*100}%`)}updateCurrentBox(){if(!this.shadowRoot.querySelector('slot[name="current"]').assignedElements().length)return;const i=ue(this.shadowRoot,"#current-rail"),a=ue(this.shadowRoot,'[part~="current-box"]'),s=Le(this,Oa,Sn).call(this,Q(this,xa)),r=Le(this,Ua,In).call(this,s,this.range.valueAsNumber),o=Le(this,$a,kn).call(this,s,this.range.valueAsNumber);i.style.transform=`translateX(${r})`,i.style.setProperty("--_range-width",`${s.range.width}`),a.style.setProperty("--_box-shift",`${o}`),a.style.setProperty("--_box-width",`${s.box.width}px`),a.style.setProperty("visibility","initial")}handleEvent(e){switch(super.handleEvent(e),e.type){case"input":Le(this,Qs,od).call(this);break;case"pointermove":Le(this,Ys,rd).call(this,e);break;case"pointerup":Q(this,Kt)&&Ce(this,Kt,!1);break;case"pointerdown":Ce(this,Kt,!0);break;case"pointerleave":Le(this,Di,Ha).call(this,null);break;case"transitionstart":ai(e.target,this)&&setTimeout(()=>Q(this,zt).call(this),0);break}}};Vt=new WeakMap;bt=new WeakMap;Na=new WeakMap;wi=new WeakMap;Pa=new WeakMap;xa=new WeakMap;Li=new WeakMap;Ri=new WeakMap;Gt=new WeakMap;Kt=new WeakMap;zt=new WeakMap;zs=new WeakSet;nd=function(){return this.isConnected&&!this.mediaPaused&&!this.mediaLoading&&!this.mediaEnded&&this.mediaSeekableEnd>0&&hl(this)};qs=new WeakMap;Oa=new WeakSet;Sn=function(t){var e;const a=((e=this.getAttribute("bounds")?Oi(this,`#${this.getAttribute("bounds")}`):this.parentElement)!=null?e:this).getBoundingClientRect(),s=this.range.getBoundingClientRect(),r=t.offsetWidth,o=-(s.left-a.left-r/2),l=a.right-s.left-r/2;return{box:{width:r,min:o,max:l},bounds:a,range:s}};Ua=new WeakSet;In=function(t,e){let i=`${e*100}%`;const{width:a,min:s,max:r}=t.box;if(!a)return i;if(Number.isNaN(s)||(i=`max(${`calc(1 / var(--_range-width) * 100 * ${s}% + var(--media-box-padding-left))`}, ${i})`),!Number.isNaN(r)){const l=`calc(1 / var(--_range-width) * 100 * ${r}% - var(--media-box-padding-right))`;i=`min(${i}, ${l})`}return i};$a=new WeakSet;kn=function(t,e){const{width:i,min:a,max:s}=t.box,r=e*t.range.width;if(r<a+Q(this,Li)){const o=t.range.left-t.bounds.left-Q(this,Li);return`${r-i/2+o}px`}if(r>s-Q(this,Ri)){const o=t.bounds.right-t.range.right-Q(this,Ri);return`${r+i/2-o-t.range.width}px`}return 0};Ys=new WeakSet;rd=function(t){const e=[...Q(this,Na)].some(u=>t.composedPath().includes(u));if(!this.dragging&&(e||!t.composedPath().includes(this))){Le(this,Di,Ha).call(this,null);return}const i=this.mediaSeekableEnd;if(!i)return;const a=ue(this.shadowRoot,"#preview-rail"),s=ue(this.shadowRoot,'[part~="preview-box"]'),r=Le(this,Oa,Sn).call(this,Q(this,Pa));let o=(t.clientX-r.range.left)/r.range.width;o=Math.max(0,Math.min(1,o));const l=Le(this,Ua,In).call(this,r,o),c=Le(this,$a,kn).call(this,r,o);a.style.transform=`translateX(${l})`,a.style.setProperty("--_range-width",`${r.range.width}`),s.style.setProperty("--_box-shift",`${c}`),s.style.setProperty("--_box-width",`${r.box.width}px`);const p=Math.round(Q(this,wi))-Math.round(o*i);Math.abs(p)<1&&o>.01&&o<.99||(Ce(this,wi,o*i),Le(this,Di,Ha).call(this,Q(this,wi)))};Di=new WeakSet;Ha=function(t){this.dispatchEvent(new f.CustomEvent(w.MEDIA_PREVIEW_REQUEST,{composed:!0,bubbles:!0,detail:t}))};Qs=new WeakSet;od=function(){Q(this,bt).stop();const t=ld(this);this.dispatchEvent(new f.CustomEvent(w.MEDIA_SEEK_REQUEST,{composed:!0,bubbles:!0,detail:t}))};cs.shadowRootOptions={mode:"open"};cs.getContainerTemplateHTML=Xf;f.customElements.get("media-time-range")||f.customElements.define("media-time-range",cs);var Zf=cs,Jf=(t,e,i)=>{if(!e.has(t))throw TypeError("Cannot "+i)},Dr=(t,e,i)=>(Jf(t,e,"read from private field"),i?i.call(t):e.get(t)),ev=(t,e,i)=>{if(e.has(t))throw TypeError("Cannot add the same private member more than once");e instanceof WeakSet?e.add(t):e.set(t,i)},wa;const tv=1,iv=t=>t.mediaMuted?0:t.mediaVolume,av=t=>`${Math.round(t*100)}%`;let dd=class extends St{constructor(){super(...arguments),ev(this,wa,()=>{const e=this.range.value,i=new f.CustomEvent(w.MEDIA_VOLUME_REQUEST,{composed:!0,bubbles:!0,detail:e});this.dispatchEvent(i)})}static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_VOLUME,d.MEDIA_MUTED,d.MEDIA_VOLUME_UNAVAILABLE]}connectedCallback(){super.connectedCallback(),this.range.setAttribute("aria-label",k("volume")),this.range.addEventListener("input",Dr(this,wa))}disconnectedCallback(){this.range.removeEventListener("input",Dr(this,wa)),super.disconnectedCallback()}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),(e===d.MEDIA_VOLUME||e===d.MEDIA_MUTED)&&(this.range.valueAsNumber=iv(this),this.range.setAttribute("aria-valuetext",av(this.range.valueAsNumber)),this.updateBar())}get mediaVolume(){return J(this,d.MEDIA_VOLUME,tv)}set mediaVolume(e){fe(this,d.MEDIA_VOLUME,e)}get mediaMuted(){return j(this,d.MEDIA_MUTED)}set mediaMuted(e){F(this,d.MEDIA_MUTED,e)}get mediaVolumeUnavailable(){return ee(this,d.MEDIA_VOLUME_UNAVAILABLE)}set mediaVolumeUnavailable(e){te(this,d.MEDIA_VOLUME_UNAVAILABLE,e)}};wa=new WeakMap;f.customElements.get("media-volume-range")||f.customElements.define("media-volume-range",dd);var sv=dd;function nv(t){return`
      <style>
        :host {
          min-width: 4ch;
          padding: var(--media-button-padding, var(--media-control-padding, 10px 5px));
          width: 100%;
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 1rem;
          font-weight: var(--media-button-font-weight, normal);
        }

        #checked-indicator {
          display: none;
        }

        :host([${d.MEDIA_LOOP}]) #checked-indicator {
          display: block;
        }
      </style>
      
      <span id="icon">
     </span>

      <div id="checked-indicator">
        <svg aria-hidden="true" viewBox="0 1 24 24" part="checked-indicator indicator">
          <path d="m10 15.17 9.193-9.191 1.414 1.414-10.606 10.606-6.364-6.364 1.414-1.414 4.95 4.95Z"/>
        </svg>
      </div>
    `}function rv(){return k("Loop")}class us extends ve{constructor(){super(...arguments),this.container=null}static get observedAttributes(){return[...super.observedAttributes,d.MEDIA_LOOP]}connectedCallback(){var e;super.connectedCallback(),this.container=((e=this.shadowRoot)==null?void 0:e.querySelector("#icon"))||null,this.container&&(this.container.textContent=k("Loop"))}attributeChangedCallback(e,i,a){super.attributeChangedCallback(e,i,a),e===d.MEDIA_LOOP&&this.container&&this.setAttribute("aria-checked",this.mediaLoop?"true":"false")}get mediaLoop(){return j(this,d.MEDIA_LOOP)}set mediaLoop(e){F(this,d.MEDIA_LOOP,e)}handleClick(){const e=!this.mediaLoop,i=new f.CustomEvent(w.MEDIA_LOOP_REQUEST,{composed:!0,bubbles:!0,detail:e});this.dispatchEvent(i)}}us.getSlotTemplateHTML=nv;us.getTooltipContentHTML=rv;f.customElements.get("media-loop-button")||f.customElements.define("media-loop-button",us);var ov=us;function K(t){if(typeof t=="boolean")return t?"":void 0;if(typeof t=="function")return;const e=i=>typeof i=="string"||typeof i=="number"||typeof i=="boolean";if(Array.isArray(t)&&t.every(e))return t.join(" ");if(!(typeof t=="object"&&t!==null))return t}G({tagName:"media-gesture-receiver",elementClass:As,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-container",elementClass:rm,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});const lv=G({tagName:"media-controller",elementClass:Fm,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-tooltip",elementClass:Cs,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-chrome-button",elementClass:zm,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-airplay-button",elementClass:Qm,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-captions-button",elementClass:tp,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-cast-button",elementClass:rp,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-chrome-dialog",elementClass:dp,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-chrome-range",elementClass:hp,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});const dv=G({tagName:"media-control-bar",elementClass:fp,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-text-display",elementClass:bp,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});const cv=G({tagName:"media-duration-display",elementClass:Tp,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-error-dialog",elementClass:Lp,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-keyboard-shortcuts-dialog",elementClass:Pp,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-fullscreen-button",elementClass:Bp,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-live-button",elementClass:qp,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-loading-indicator",elementClass:Xp,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});const uv=G({tagName:"media-mute-button",elementClass:af,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-pip-button",elementClass:rf,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-playback-rate-button",elementClass:hf,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});const hv=G({tagName:"media-play-button",elementClass:gf,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-poster-image",elementClass:Af,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-preview-chapter-display",elementClass:wf,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-preview-thumbnail",elementClass:Vs,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-preview-time-display",elementClass:Cf,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-seek-backward-button",elementClass:Of,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-seek-forward-button",elementClass:Wf,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});const mv=G({tagName:"media-time-display",elementClass:zf,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}}),pv=G({tagName:"media-time-range",elementClass:Zf,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}}),fv=G({tagName:"media-volume-range",elementClass:sv,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});G({tagName:"media-loop-button",elementClass:ov,react:V,toAttributeValue:K,defaultProps:{suppressHydrationWarning:!0}});const vv=({children:t,style:e,...i})=>n.jsx(lv,{audio:!0,"data-slot":"audio-player",style:{"--media-background-color":"transparent","--media-button-icon-height":"1rem","--media-button-icon-width":"1rem","--media-control-background":"transparent","--media-control-hover-background":"var(--color-accent)","--media-control-padding":"0","--media-font":"var(--font-sans)","--media-font-size":"0.75rem","--media-icon-color":"var(--color-foreground)","--media-preview-time-background":"var(--color-background)","--media-preview-time-border-radius":"var(--radius-md)","--media-preview-time-text-shadow":"none","--media-primary-color":"var(--color-primary)","--media-range-bar-color":"var(--color-primary)","--media-range-track-background":"var(--color-border)","--media-secondary-color":"var(--color-muted-foreground)","--media-text-color":"var(--color-foreground)","--media-tooltip-arrow-display":"none","--media-tooltip-background":"var(--color-background)","--media-tooltip-border-radius":"var(--radius-md)",...e},...i,children:t}),gv=({...t})=>n.jsx("audio",{"data-slot":"audio-player-element",slot:"media",src:"src"in t?t.src:`data:${t.data.mediaType};base64,${t.data.base64}`,...t}),Ev=({children:t,...e})=>n.jsx(dv,{"data-slot":"audio-player-control-bar",...e,children:n.jsx(Jc,{orientation:"horizontal",children:t})}),bv=({className:t,...e})=>n.jsx(ke,{asChild:!0,size:"icon-sm",variant:"outline",children:n.jsx(hv,{className:P("bg-transparent",t),"data-slot":"audio-player-play-button",...e})}),_v=({className:t,...e})=>n.jsx(Pi,{asChild:!0,className:"bg-transparent",children:n.jsx(mv,{className:P("tabular-nums",t),"data-slot":"audio-player-time-display",...e})}),Av=({className:t,...e})=>n.jsx(Pi,{asChild:!0,className:"bg-transparent",children:n.jsx(pv,{className:P("",t),"data-slot":"audio-player-time-range",...e})}),yv=({className:t,...e})=>n.jsx(Pi,{asChild:!0,className:"bg-transparent",children:n.jsx(cv,{className:P("tabular-nums",t),"data-slot":"audio-player-duration-display",...e})}),Tv=({className:t,...e})=>n.jsx(Pi,{asChild:!0,className:"bg-transparent",children:n.jsx(uv,{className:P("",t),"data-slot":"audio-player-mute-button",...e})}),xv=({className:t,...e})=>n.jsx(Pi,{asChild:!0,className:"bg-transparent",children:n.jsx(fv,{className:P("",t),"data-slot":"audio-player-volume-range",...e})}),wv=window.location.origin;function Sv(t){return t.startsWith("http://")||t.startsWith("https://")?t:`${wv}${t.startsWith("/")?"":"/"}${t}`}function Iv({message:t,agentName:e,agentColor:i,status:a,loadingType:s="default",onFeedback:r,scrollToBottomAfterPaint:o}){var E,m,v,g,_,A,b,T,S,M,I;const{user:l}=vc(),c=t.from==="user";(E=t.versions[0])!=null&&E.id;const p="",u=l!=null&&l.full_name?Jt(l.full_name):"You";return n.jsxs("div",{className:P("flex gap-3 group relative","flex-row"),children:[n.jsx(Zt,{variant:c?"chat_user":"chat_ai",color:c?void 0:i||tn,children:c?u:Jt(e)}),n.jsxs("div",{className:"flex-1 min-w-0",children:[n.jsxs("div",{className:"flex items-center gap-2 mb-1",children:[n.jsx("span",{className:"text-sm font-medium text-zinc-900",children:c?"You":e}),p]}),t.tools&&t.tools.length>0?t.tools.map((x,L)=>n.jsxs(th,{children:[n.jsx(ah,{title:x.name,type:`tool-${x.name}`,state:x.status}),n.jsxs(sh,{children:[n.jsx(nh,{input:x.parameters}),n.jsx(rh,{output:x.result,errorText:x.error})]})]},`${t.key}-tool-${L}`)):n.jsxs(eu,{from:t.from,className:P(c&&"!ml-0",!c&&"!max-w-full"),children:[n.jsxs(tu,{className:P(c&&"!ml-0",!c&&"w-full"),children:[(a==="submitted"||a==="streaming")&&t.from==="assistant"&&(!((m=t.versions[0])!=null&&m.content)||t.versions[0].content.trim()==="")&&n.jsx(Ih,{type:(v=t.tools)!=null&&v.length?"tool-execution":s,hasTools:!!t.tools&&t.tools.length>0,toolName:(_=(g=t.tools)==null?void 0:g[0])==null?void 0:_.name}),t.generatedAudio&&t.from==="assistant"?n.jsx("div",{className:"w-full max-w-md",children:n.jsxs(vv,{children:[n.jsx(gv,{src:Sv(t.generatedAudio)}),n.jsxs(Ev,{children:[n.jsx(bv,{}),n.jsx(_v,{}),n.jsx(Av,{}),n.jsx(yv,{}),n.jsx(Tv,{}),n.jsx(xv,{})]})]})}):t.kind==="Image"?n.jsxs("div",{className:"flex flex-col gap-2",children:[t.generatedImage?n.jsx(kh,{src:t.generatedImage,alt:((A=t.versions[0])==null?void 0:A.content)||"Generated image",className:"max-w-full h-auto rounded-lg border max-h-[512px] object-contain",showDownloadButton:!0,onLoad:()=>o(!1)}):n.jsx(Ie,{className:"w-full h-[512px] rounded-lg"}),((b=t.versions[0])==null?void 0:b.content)&&n.jsx(er,{content:t.versions[0].content,messageKey:t.key})]}):!t.generatedAudio&&!((a==="submitted"||a==="streaming")&&t.from==="assistant"&&(!((T=t.versions[0])!=null&&T.content)||t.versions[0].content.trim()==="")&&!t.tools)&&n.jsx(er,{content:((S=t.versions[0])==null?void 0:S.content)||"",messageKey:t.key})]}),t.from==="assistant"&&((M=t.versions[0])==null?void 0:M.content)&&!t.tools&&n.jsx("div",{className:"opacity-0 transition-opacity group-hover:opacity-100",children:n.jsx(Th,{content:t.versions[0].content,onFeedback:r,agentMessageId:t.versions[0].id})}),t.from==="user"&&((I=t.versions[0])==null?void 0:I.content)&&n.jsx("div",{className:"opacity-0 transition-opacity group-hover:opacity-100 flex items-center gap-2 text-muted-foreground",children:n.jsx(Qo,{content:t.versions[0].content})})]})]})]})}function kv({children:t}){return n.jsx("kbd",{className:"flex items-center gap-2 font-sans border border-zinc-300 rounded px-1",children:t})}function Mv({className:t,...e}){return n.jsx(Fd,{role:"status","aria-label":"Loading",className:P("size-4 animate-spin",t),...e})}const Cv=()=>typeof window>"u"?"none":"SpeechRecognition"in window||"webkitSpeechRecognition"in window?"speech-recognition":"MediaRecorder"in window&&"mediaDevices"in navigator?"media-recorder":"none",Lv=({className:t,onTranscriptionChange:e,onAudioRecorded:i,lang:a="en-US",...s})=>{const[r,o]=h.useState(!1),[l,c]=h.useState(!1),[p]=h.useState(Cv),[u,E]=h.useState(!1),m=h.useRef(null),v=h.useRef(null),g=h.useRef(null),_=h.useRef([]),A=h.useRef(e),b=h.useRef(i);A.current=e,b.current=i,h.useEffect(()=>{if(p!=="speech-recognition")return;const x=window.SpeechRecognition||window.webkitSpeechRecognition,L=new x;L.continuous=!0,L.interimResults=!0,L.lang=a;const $=()=>{o(!0)},ie=()=>{o(!1)},R=ae=>{var ne,N;const B=ae;let se="";for(let re=B.resultIndex;re<B.results.length;re+=1){const U=B.results[re];U.isFinal&&(se+=((ne=U[0])==null?void 0:ne.transcript)??"")}se&&((N=A.current)==null||N.call(A,se))},H=()=>{o(!1)};return L.addEventListener("start",$),L.addEventListener("end",ie),L.addEventListener("result",R),L.addEventListener("error",H),m.current=L,E(!0),()=>{L.removeEventListener("start",$),L.removeEventListener("end",ie),L.removeEventListener("result",R),L.removeEventListener("error",H),L.stop(),m.current=null,E(!1)}},[p,a]),h.useEffect(()=>()=>{var x;if(((x=v.current)==null?void 0:x.state)==="recording"&&v.current.stop(),g.current)for(const L of g.current.getTracks())L.stop()},[]);const T=h.useCallback(async()=>{if(b.current)try{const x=await navigator.mediaDevices.getUserMedia({audio:!0});g.current=x;const L=new MediaRecorder(x);_.current=[];const $=H=>{H.data.size>0&&_.current.push(H.data)},ie=async()=>{var ae;for(const B of x.getTracks())B.stop();g.current=null;const H=new Blob(_.current,{type:"audio/webm"});if(H.size>0&&b.current){c(!0);try{const B=await b.current(H);B&&((ae=A.current)==null||ae.call(A,B))}catch{}finally{c(!1)}}},R=()=>{o(!1);for(const H of x.getTracks())H.stop();g.current=null};L.addEventListener("dataavailable",$),L.addEventListener("stop",ie),L.addEventListener("error",R),v.current=L,L.start(),o(!0)}catch{o(!1)}},[]),S=h.useCallback(()=>{var x;((x=v.current)==null?void 0:x.state)==="recording"&&v.current.stop(),o(!1)},[]),M=h.useCallback(()=>{p==="speech-recognition"&&m.current?r?m.current.stop():m.current.start():p==="media-recorder"&&(r?S():T())},[p,r,T,S]),I=p==="none"||p==="speech-recognition"&&!u||p==="media-recorder"&&!i||l;return n.jsxs("div",{className:"relative inline-flex items-center justify-center",children:[r&&[0,1,2].map(x=>n.jsx("div",{className:"absolute inset-0 animate-ping rounded-full border-2 border-red-400/30",style:{animationDelay:`${x*.3}s`,animationDuration:"2s"}},x)),n.jsxs(ke,{variant:"secondary",className:P("relative z-10 rounded-full transition-all duration-300",r?"bg-destructive text-destructive-foreground hover:bg-destructive/90 hover:text-destructive-foreground":"bg-secondary text-secondary-foreground hover:bg-secondary/80",t),disabled:I,onClick:M,...s,children:[l&&n.jsx(Mv,{}),!l&&r&&n.jsx(Wd,{className:"size-4"}),!(l||r)&&n.jsx(jr,{className:"size-4"})]})]})};function Rv({chatId:t,agentName:e,onConversationCreated:i,onStatusChange:a,onLoadingTypeChange:s,isCreatingConversationRef:r,newlyCreatedConversationIdRef:o,setMessages:l,isModelMismatch:c=!1,scrollToBottomAfterPaint:p}){const u=Ni(),[E,m]=h.useState(""),[v,g]=h.useState(!1),_=h.useRef(null),A=h.useRef(!1),b=60,T=200;h.useEffect(()=>{const R=setTimeout(()=>{_.current&&_.current.focus()},100);return()=>clearTimeout(R)},[t]);const S=h.useCallback(async R=>{var re,U;const H=qn,B=(await gc({agent:e,message:R.message,conversationId:R.conversationId},{useStreaming:H,onDelta:H?R.updateAssistantContent:void 0})).message,se=(B==null?void 0:B.conversation_id)??((re=B==null?void 0:B.run)==null?void 0:re.conversation_id),ne=((U=B==null?void 0:B.run)==null?void 0:U.response)??(B==null?void 0:B.response),N=typeof ne=="string"?ne:"";return!H&&N&&R.updateAssistantContent(N),{conversationId:se}},[e]),M=h.useCallback(async R=>{if(R.preventDefault(),!E.trim()||!e||v)return;const H=E.trim();g(!0),a("submitted");const ae=`user-${Date.now()}`,B={key:ae,from:"user",versions:[{id:ae,content:H}]};l(N=>[...N,B]),m(""),_.current&&_.current.focus();const se=`assistant-${Date.now()}`;l(N=>[...N,{key:se,from:"assistant",versions:[{id:se,content:""}]}]);const ne=N=>{l(re=>re.map(U=>U.key===se?{...U,versions:[{id:se,content:N}]}:U)),p==null||p(!1)};try{t||(r.current=!0);const{conversationId:N}=await S({message:H,conversationId:t??void 0,assistantMessageId:se,updateAssistantContent:ne});a("ready"),N&&i?(o.current=N,i(N,e),setTimeout(()=>{r.current=!1},500)):r.current=!1,setTimeout(()=>{var re;return(re=_.current)==null?void 0:re.focus()},t?100:200)}catch(N){qn&&bc(!1),r.current=!1,a("error"),be.error("Failed to send message",{description:N instanceof Error?N.message:"An error occurred"}),l(re=>re.filter(U=>U.key!==se))}finally{g(!1)}},[E,e,t,i,v,a,r,o,l,p,S]),I=h.useCallback(async R=>{const H=`recording-${Date.now()}.webm`,ae=new FileReader,B=await new Promise((N,re)=>{ae.onloadend=()=>{const U=ae.result,O=U.includes(",")?U.split(",")[1]:U;N(O??"")},ae.onerror=re,ae.readAsDataURL(R)}),se=`user-${Date.now()}`,ne=`assistant-${Date.now()}`;l(N=>[...N,{key:ne,from:"assistant",versions:[{id:ne,content:""}]}]),a("submitted"),s==null||s("transcribing");try{const N=await Ec({filename:H,b64data:B,agent:e,conversation:t??void 0});if(!(N!=null&&N.success)||!N.transcript)throw l(U=>U.filter(O=>O.key!==ne)),new Error(typeof(N==null?void 0:N.error)=="string"?N.error:"Transcription failed");A.current=!0,l(U=>{const O=U.findIndex(Te=>Te.key===ne),q={key:se,from:"user",versions:[{id:se,content:N.transcript}]};return O<0?[...U,q]:[...U.slice(0,O),q,...U.slice(O)]}),s==null||s("default"),t||(r.current=!0);const re=U=>{l(O=>O.map(q=>q.key===ne?{...q,versions:[{id:ne,content:U}]}:q)),p==null||p(!1)};try{return await S({message:N.transcript,conversationId:N.conversation_id,assistantMessageId:ne,updateAssistantContent:re}),a("ready"),N.conversation_id&&i&&(o.current=N.conversation_id,i(N.conversation_id,e)),N.transcript}catch(U){throw r.current=!1,l(O=>O.filter(q=>q.key!==ne)),a("error"),be.error("Failed to send message",{description:U instanceof Error?U.message:"An error occurred"}),U}}catch(N){throw a("error"),s==null||s("default"),r.current=!1,be.error("Failed to transcribe or send",{description:N instanceof Error?N.message:"An error occurred"}),N}},[e,t,i,a,s,r,o,l,p,S]),x=h.useCallback(R=>{if(A.current){A.current=!1;return}m(H=>H?`${H} ${R}`:R)},[]),L=h.useCallback(R=>{R.key==="Enter"&&!R.shiftKey&&(R.preventDefault(),M(R))},[M]),$=h.useCallback(()=>{const R=_.current;R&&requestAnimationFrame(()=>{requestAnimationFrame(()=>{if(!R)return;const H=R.style.minHeight;R.style.height="1px",R.style.minHeight="0",R.style.overflowY="hidden",R.offsetHeight;const ae=R.scrollHeight;R.style.minHeight=H||"";const B=Math.min(Math.max(ae,b),T);R.style.height=`${B}px`,ae>T?R.style.overflowY="auto":R.style.overflowY="hidden"})})},[]);h.useEffect(()=>{if(_.current){if(!E){const R=_.current;R.style.height=`${b}px`,R.style.overflowY="hidden";return}$()}},[E,$]);const ie=h.useCallback(()=>{e&&u(`/chat/new?agent=${e}`)},[u,e]);return e?c&&t?n.jsx("div",{className:"px-6 pb-6 pt-2",children:n.jsx("div",{className:"w-full border border-zinc-200 rounded-xl bg-zinc-50 p-6",children:n.jsxs("div",{className:"flex flex-col items-center justify-center gap-4 text-center",children:[n.jsx("p",{className:"text-sm text-zinc-600",children:"Model changed, please start a new conversation"}),n.jsxs(ke,{onClick:ie,className:"gap-2",children:[n.jsx(Xs,{className:"w-4 h-4"}),"New Conversation"]})]})})}):n.jsxs("div",{className:"px-6 pb-6 pt-2",children:[n.jsx("form",{onSubmit:M,className:"flex gap-2 items-end",children:n.jsxs("div",{className:"w-full border border-zinc-200 rounded-xl shadow-2xl focus-within:ring-1 focus-within:ring-ring transition-all",children:[n.jsx(Kr,{ref:_,value:E,onChange:R=>{m(R.target.value)},rows:2,onKeyDown:L,placeholder:"Type your message...",className:"p-4 w-full min-h-[60px] max-h-[200px] resize-none focus-visible:ring-0 border-none shadow-none",style:{height:`${b}px`},disabled:v||c}),n.jsxs("div",{className:"px-3 pb-3 w-full flex items-center justify-end gap-x-2 mt-2",children:[n.jsxs("span",{className:"flex items-center gap-x-1 text-[10px] text-zinc-400",children:["Use",n.jsx(kv,{children:"Shift + Enter"}),"for new line"]}),!E.trim()&&n.jsx(Lv,{onTranscriptionChange:x,onAudioRecorded:I,disabled:v||c,size:"icon",className:"shrink-0 rounded-full"}),n.jsx(ke,{type:"submit",disabled:!E.trim()||v||c,size:"icon",className:"shrink-0",children:n.jsx(Bd,{})})]})]})}),n.jsx("p",{className:"mt-3 text-[10px] text-zinc-400 text-center",children:"AI output can be inaccurate. Double check important info."})]}):null}function Dv(){const t=Ni(),[e,i]=h.useState([]),[a,s]=h.useState(!0),[r,o]=h.useState("");h.useEffect(()=>{let p=!1;async function u(){s(!0);try{const E=await Es();p||i(E.slice(0,5))}catch(E){console.error("Error fetching recent agents:",E)}finally{p||s(!1)}}return u(),()=>{p=!0}},[]);const l=h.useCallback(p=>{o(p),t(`/chat/new?agent=${p}`)},[t]),c=h.useCallback(p=>{t(`/chat/new?agent=${p}`)},[t]);return n.jsx("div",{className:"flex-1 flex items-center justify-center",children:n.jsxs("div",{className:"text-center space-y-6 max-w-md w-full px-6",children:[n.jsxs("div",{className:"space-y-2",children:[n.jsx("p",{className:"text-sm text-muted-foreground",children:"Select an agent to start chatting"}),n.jsx("div",{className:"flex justify-center",children:n.jsx(zr,{value:r,onValueChange:l,showLabel:!0})})]}),e.length>0&&n.jsxs("div",{className:"space-y-3",children:[n.jsx("p",{className:"text-xs font-medium text-zinc-500 uppercase tracking-wider",children:"Recently used agents"}),n.jsx("div",{className:"flex flex-wrap gap-2 justify-center",children:a?Array.from({length:6}).map((p,u)=>n.jsx(Ie,{className:"h-10 w-24 rounded-lg"},u)):e.map(p=>n.jsxs(ke,{variant:"outline",size:"sm",onClick:()=>c(p.name),className:"gap-2 hover:bg-zinc-100",children:[n.jsx(Zt,{variant:"listing_ai",color:p.agent_color||tn,children:Jt(p.agent_name)}),n.jsx("span",{className:"text-xs font-medium text-zinc-700",children:p.agent_name})]},p.name))})]})]})})}function Nv(t,e){const[i,a]=h.useState(""),[s,r]=h.useState(null);return h.useEffect(()=>{let o=!1;async function l(p){try{const u=await Fa(p);if(!(u!=null&&u.agent))return;o||a(u.agent);try{const E=await Si(u.agent);o||r(E.agent_color||null)}catch(E){console.error("Failed to load agent color",E),o||r(null)}}catch(u){console.error("Failed to load conversation agent",u)}}async function c(){const p=e.get("agent")??"";if(o||a(p),!p){o||r(null);return}try{const u=await Si(p);o||r(u.agent_color||null)}catch(u){console.error("Failed to load agent color",u),o||r(null)}}return t?l(t):c(),()=>{o=!0}},[t,e]),{agentName:i,agentColor:s}}function Pv(t){const{chatId:e,initialLoading:i,messages:a}=t,s=h.useRef(null),r=h.useRef(null),o=h.useRef(null),l=h.useCallback((p=!1)=>{const u=s.current;u&&u.scrollTo({top:u.scrollHeight,behavior:p?"auto":"smooth"})},[]),c=h.useCallback((p=!1)=>{requestAnimationFrame(()=>{requestAnimationFrame(()=>{l(p)})})},[l]);return h.useEffect(()=>{var u;if(i||a.length===0)return;const p=e??"__new_chat__";o.current!==p&&(c(!0),r.current=((u=a[a.length-1])==null?void 0:u.key)??null,o.current=p)},[i,e,a.length,c]),h.useEffect(()=>{var u;if(i||a.length===0)return;const p=((u=a[a.length-1])==null?void 0:u.key)??null;p!==r.current&&c(!1),r.current=p},[a,i,c]),{scrollContainerRef:s,scrollToBottomAfterPaint:c}}function Ov(t){const e=t.tool_status??t.status??"Queued";let i=t.tool_result;if(!i&&typeof t.result=="string")try{const a=JSON.parse(t.result);i=a&&typeof a=="object"?a:void 0}catch{i={output:t.result}}return{...t,agent_run_id:t.agent_run_id??"",conversation_id:t.conversation_id??"",message_id:t.message_id??t.agent_run_id??"",tool_call_id:t.tool_call_id??"",tool_name:t.tool_name??"unknown",tool_status:e,tool_args:t.tool_args,tool_result:i,error:t.error??void 0}}function cd(t){if(!t)return{};if(typeof t=="object")return t;if(typeof t!="string")return{};try{const e=JSON.parse(t);return e&&typeof e=="object"?e:{}}catch{return{}}}function Uv(t){if(t==null)return"";if(typeof t=="string")return t;try{return JSON.stringify(t,null,2)}catch{return String(t)}}function $v(t,e){const i=Ov((typeof(e==null?void 0:e.type)=="string",e));if(!i.tool_call_id&&!i.tool_name)return t;const a=i.tool_name&&i.tool_name!=="unknown"?i.tool_name:"Tool",s=cd(i.tool_args),r=i.tool_result?Uv(i.tool_result):void 0,o={tool_call_id:i.tool_call_id,name:a,description:a,status:Xo(i.tool_status),parameters:s,result:i.tool_status==="Completed"?r:void 0,error:i.tool_status==="Failed"?i.error||r:void 0};let l=i.agent_run_id?t.findIndex(u=>u.key===i.agent_run_id):-1;if(l<0&&i.tool_call_id&&(l=t.findIndex(u=>{var E;return(E=u.tools)==null?void 0:E.some(m=>m.tool_call_id===i.tool_call_id)})),l>=0){const u=t[l],E=u.tools||[];let m=i.tool_call_id?E.findIndex(A=>A.tool_call_id===i.tool_call_id):-1;m<0&&(m=E.findIndex(A=>A.name===a||A.name===i.tool_name));const v=[...E];m>=0?v[m]=o:v.push(o);const g=i.tool_name==="generate_image"&&i.type==="tool_call_started",_=[...t];return _[l]={...u,kind:g?"Image":u.kind,tools:v},_}if(!i.agent_run_id)return t;const c=i.tool_name==="generate_image"&&i.type==="tool_call_started",p={key:i.agent_run_id,from:"assistant",kind:c?"Image":void 0,versions:[{id:i.message_id||i.agent_run_id,content:""}],tools:[o]};return[...t,p]}function Hv(t,e){const i=t.findIndex(s=>s.versions.some(r=>r.id===e.message_id));if(i>=0){const s=[...t];return s[i]={...s[i],kind:e.kind,generatedImage:e.generated_image,generatedAudio:e.generated_audio,versions:s[i].versions.map(r=>r.id===e.message_id?{...r,content:e.content||r.content}:r)},s}const a={key:e.message_id,from:"assistant",kind:e.kind,generatedImage:e.generated_image,generatedAudio:e.generated_audio,versions:[{id:e.message_id,content:e.content||""}]};return[...t,a]}function Nr(t,e,i=!1){if(i&&e.length===0||e.length===0)return t;const a=e.map(o=>{const l=t.find(u=>u.key===o.id),c=(l==null?void 0:l.tools)||[],p={key:o.id,from:o.isAgent?"assistant":"user",kind:o.kind,generatedImage:o.generatedImage,generatedAudio:o.generatedAudio,voiceMessage:o.voiceMessage,versions:[{id:o.id,content:o.content}]};if(o.kind==="Tool Result"&&o.toolName){const u=cd(o.toolArgs),E=c.find(_=>_.name===o.toolName),m=(E==null?void 0:E.tool_call_id)||`temp-${o.id}-${o.toolName}`,v={tool_call_id:m,name:o.toolName,description:o.toolName,status:Xo(o.toolStatus),parameters:u,result:o.toolStatus==="Completed"?o.content:void 0,error:o.toolStatus==="Failed"?o.content:void 0},g=new Map;c.forEach(_=>{g.set(_.tool_call_id,_)}),g.has(m)||g.set(m,v),p.tools=Array.from(g.values())}else c.length>0&&(p.tools=c);return p}),s=new Set(e.map(o=>o.id)),r=i?t.filter(o=>!s.has(o.key)):t.filter(o=>!s.has(o.key)&&o.tools&&o.tools.length>0);return[...a,...r]}function jv({chatId:t,onConversationCreated:e}){const{chatId:i}=ja(),[a]=Fr(),s=t??(i&&i!=="new"?i:null),r=!s,[o,l]=h.useState([]),[c,p]=h.useState("ready"),[u,E]=h.useState("default"),m=h.useRef(!1),v=h.useRef(null),[g,_]=h.useState(!1),[A,b]=h.useState(!1),{agentName:T,agentColor:S}=Nv(s,a);h.useEffect(()=>{if(!s||!T){_(!1);return}let O=!1;async function q(){try{const[Te,pt]=await Promise.all([Fa(s),Si(T)]);if(O)return;Te!=null&&Te.model&&(pt!=null&&pt.model)?_(Te.model!==pt.model):_(!1)}catch(Te){console.error("Error checking model mismatch:",Te),O||_(!1)}}return q(),()=>{O=!0}},[s,T]);const M=h.useMemo(()=>s?{conversation:s}:{},[s]),I=h.useMemo(()=>!!s&&!A,[s,A]);h.useEffect(()=>{if(s&&v.current===s){b(!0);const O=setTimeout(()=>{b(!1)},800);return()=>clearTimeout(O)}else s&&v.current!==s&&b(!1)},[s]);const{items:x,initialLoading:L,loadingMore:$,hasMore:ie,sentinelRef:R,error:H}=Js({fetchFn:async O=>{if(!s)return{data:[],hasMore:!1};const q=await _c({conversation:s,limit:O.limit||20,start:O.start||0});return{data:q.data,hasMore:q.hasMore}},initialParams:M,pageSize:20,direction:"reverse",enabled:I,autoLoad:I,autoLoadMore:I}),ae=h.useCallback(O=>{O.conversation_id===s&&l(q=>$v(q,O))},[s]),B=h.useCallback(O=>{O.conversation_id===s&&l(q=>Hv(q,O))},[s]);Xu({conversationId:s,onToolUpdate:ae,onNewMessage:B}),h.useEffect(()=>{H&&s&&be.error("Failed to load messages",{description:H.message||"An error occurred while fetching messages. Please try again.",duration:5e3})},[H,s]),h.useEffect(()=>{if(!s){m.current||l([]);return}if(!m.current){if(A){x.length>0&&l(O=>Nr(O,x,!0));return}l(O=>Nr(O,x,!1))}},[s,x,A]);const se=h.useRef(s);h.useEffect(()=>{if(s&&s!==se.current){const O=s===v.current;if(O||(l([]),b(!1)),O){const q=setTimeout(()=>{v.current=null,b(!1)},1e3);return()=>clearTimeout(q)}}se.current=s},[s]);const{scrollContainerRef:ne,scrollToBottomAfterPaint:N}=Pv({chatId:s,initialLoading:L,messages:o}),re=h.useCallback(async(O,q)=>{if(!T){be.error("Select an agent before submitting feedback");return}try{await Ac({agent:T,feedback:O,comments:q==null?void 0:q.comments,conversation:s??void 0,agent_message:q==null?void 0:q.agentMessageId}),be.success("Thanks for the feedback!")}catch(Te){console.error(Te)}},[T,s]);if(r&&!T)return n.jsx(Dv,{});const U=L&&o.length===0;return n.jsxs("div",{className:"flex-1 flex flex-col overflow-hidden min-h-0",children:[n.jsx("div",{className:"flex-1 overflow-y-auto min-h-0",ref:ne,children:n.jsx("div",{className:"max-w-4xl mx-auto px-6 py-4 space-y-4",children:U?n.jsx("div",{className:"flex items-center justify-center py-20",children:n.jsx("p",{className:"text-sm text-muted-foreground",children:"Loading messages..."})}):H&&!L?n.jsx("div",{className:"flex items-center justify-center py-20",children:n.jsxs("div",{className:"text-center",children:[n.jsx("p",{className:"text-sm text-destructive mb-2",children:"Failed to load messages"}),n.jsx("p",{className:"text-xs text-muted-foreground",children:H.message||"An error occurred while fetching messages."})]})}):o.length===0&&!r?n.jsx("div",{className:"flex items-center justify-center py-20",children:n.jsx("p",{className:"text-sm text-muted-foreground",children:"No messages yet"})}):n.jsxs("div",{className:"mt-2 space-y-8",children:[ie&&!r&&!v.current&&!m.current&&n.jsx("div",{ref:R,className:"h-2 w-full opacity-0","aria-hidden":"true"}),$&&n.jsx("div",{className:"text-xs text-muted-foreground text-center py-2",children:"Loading previous messages..."}),o.map(O=>n.jsx(Iv,{message:O,agentName:T,agentColor:S,status:c,loadingType:u,onFeedback:re,scrollToBottomAfterPaint:N},O.key))]})})}),n.jsx("div",{className:"max-w-4xl mx-auto w-full shrink-0",children:n.jsx(Rv,{chatId:s,agentName:T,onConversationCreated:e,onStatusChange:p,onLoadingTypeChange:E,isCreatingConversationRef:m,newlyCreatedConversationIdRef:v,setMessages:l,isModelMismatch:g,scrollToBottomAfterPaint:N})})]})}function Fv({chatId:t,onConversationCreated:e}){const{setOpen:i}=yc();return h.useEffect(()=>{i(!1)},[]),n.jsxs("div",{className:"w-full h-full flex flex-col overflow-hidden bg-background",children:[n.jsx(Qu,{chatId:t}),n.jsx(jv,{chatId:t,onConversationCreated:e})]})}function Eg(){const t=Ni(),{chatId:e}=ja(),i=e&&e!=="new"?e:null,[a,s]=h.useState(!0),r=h.useCallback(()=>s(l=>!l),[]),o=h.useCallback((l,c)=>{const p=new CustomEvent("ivendnext_ai_agents:conversation-created",{detail:{conversationId:l,agentName:c}});window.dispatchEvent(p),t(`/chat/${l}`)},[t]);return n.jsxs("section",{className:"flex h-full overflow-hidden relative",children:[n.jsx("div",{className:P("shrink-0 transition-all duration-200 ease-in-out overflow-hidden",a?"w-80":"w-0"),children:n.jsx("div",{className:"w-80 h-full",children:n.jsx(Gu,{})})}),n.jsxs("div",{className:"flex-1 min-h-0 h-full relative",children:[n.jsxs(ke,{variant:"ghost",size:"icon",onClick:r,className:"absolute top-4 left-4 z-20 h-8 w-8 text-zinc-500 hover:text-zinc-900",children:[a?n.jsx(Vd,{className:"h-4 w-4"}):n.jsx(Gd,{className:"h-4 w-4"}),n.jsx("span",{className:"sr-only",children:a?"Close sidebar":"Open sidebar"})]}),n.jsx(Fv,{chatId:i,onConversationCreated:o})]})]})}export{Eg as ChatPage,Eg as default};
