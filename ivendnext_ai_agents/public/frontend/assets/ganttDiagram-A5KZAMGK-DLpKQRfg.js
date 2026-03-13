import{a6 as ue,a5 as de,ap as fe,ao as he,a7 as me,a8 as ke,a9 as c,aa as lt,H as ye,bw as ge,bx as ve,ac as pe,p as Te,by as X,ab as nt,bz as xe,bA as zt,bB as Ht,bC as be,bD as we,bE as _e,bF as De,bG as Se,bH as Ce,bI as Me,bJ as Bt,bK as Gt,bL as jt,bM as Xt,bN as Ut,bO as Ee,ai as Ie,ag as $e,av as Le,an as Ye}from"./markdown-BWj_dXXt.js";import{d as wt,g as _t}from"./vendor-CsIv5cG4.js";import{s as vt,c as Ae}from"./xyflow-Cf6NznGc.js";import"./ui-C_bZaD0H.js";var Kt={exports:{}};(function(t,a){(function(r,i){t.exports=i()})(wt,function(){var r="day";return function(i,n,k){var y=function(A){return A.add(4-A.isoWeekday(),r)},_=n.prototype;_.isoWeekYear=function(){return y(this).year()},_.isoWeek=function(A){if(!this.$utils().u(A))return this.add(7*(A-this.isoWeek()),r);var b,F,V,N,R=y(this),M=(b=this.isoWeekYear(),F=this.$u,V=(F?k.utc:k)().year(b).startOf("year"),N=4-V.isoWeekday(),V.isoWeekday()>4&&(N+=7),V.add(N,r));return R.diff(M,"week")+1},_.isoWeekday=function(A){return this.$utils().u(A)?this.day()||7:this.day(this.day()%7?A:A-7)};var O=_.startOf;_.startOf=function(A,b){var F=this.$utils(),V=!!F.u(b)||b;return F.p(A)==="isoweek"?V?this.date(this.date()-(this.isoWeekday()-1)).startOf("day"):this.date(this.date()-1-(this.isoWeekday()-1)+7).endOf("day"):O.bind(this)(A,b)}}})})(Kt);var Fe=Kt.exports;const Oe=_t(Fe);var Jt={exports:{}};(function(t,a){(function(r,i){t.exports=i()})(wt,function(){var r={LTS:"h:mm:ss A",LT:"h:mm A",L:"MM/DD/YYYY",LL:"MMMM D, YYYY",LLL:"MMMM D, YYYY h:mm A",LLLL:"dddd, MMMM D, YYYY h:mm A"},i=/(\[[^[]*\])|([-_:/.,()\s]+)|(A|a|Q|YYYY|YY?|ww?|MM?M?M?|Do|DD?|hh?|HH?|mm?|ss?|S{1,3}|z|ZZ?)/g,n=/\d/,k=/\d\d/,y=/\d\d?/,_=/\d*[^-_:/,()\s\d]+/,O={},A=function(D){return(D=+D)+(D>68?1900:2e3)},b=function(D){return function(S){this[D]=+S}},F=[/[+-]\d\d:?(\d\d)?|Z/,function(D){(this.zone||(this.zone={})).offset=function(S){if(!S||S==="Z")return 0;var W=S.match(/([+-]|\d\d)/g),L=60*W[1]+(+W[2]||0);return L===0?0:W[0]==="+"?-L:L}(D)}],V=function(D){var S=O[D];return S&&(S.indexOf?S:S.s.concat(S.f))},N=function(D,S){var W,L=O.meridiem;if(L){for(var z=1;z<=24;z+=1)if(D.indexOf(L(z,0,S))>-1){W=z>12;break}}else W=D===(S?"pm":"PM");return W},R={A:[_,function(D){this.afternoon=N(D,!1)}],a:[_,function(D){this.afternoon=N(D,!0)}],Q:[n,function(D){this.month=3*(D-1)+1}],S:[n,function(D){this.milliseconds=100*+D}],SS:[k,function(D){this.milliseconds=10*+D}],SSS:[/\d{3}/,function(D){this.milliseconds=+D}],s:[y,b("seconds")],ss:[y,b("seconds")],m:[y,b("minutes")],mm:[y,b("minutes")],H:[y,b("hours")],h:[y,b("hours")],HH:[y,b("hours")],hh:[y,b("hours")],D:[y,b("day")],DD:[k,b("day")],Do:[_,function(D){var S=O.ordinal,W=D.match(/\d+/);if(this.day=W[0],S)for(var L=1;L<=31;L+=1)S(L).replace(/\[|\]/g,"")===D&&(this.day=L)}],w:[y,b("week")],ww:[k,b("week")],M:[y,b("month")],MM:[k,b("month")],MMM:[_,function(D){var S=V("months"),W=(V("monthsShort")||S.map(function(L){return L.slice(0,3)})).indexOf(D)+1;if(W<1)throw new Error;this.month=W%12||W}],MMMM:[_,function(D){var S=V("months").indexOf(D)+1;if(S<1)throw new Error;this.month=S%12||S}],Y:[/[+-]?\d+/,b("year")],YY:[k,function(D){this.year=A(D)}],YYYY:[/\d{4}/,b("year")],Z:F,ZZ:F};function M(D){var S,W;S=D,W=O&&O.formats;for(var L=(D=S.replace(/(\[[^\]]+])|(LTS?|l{1,4}|L{1,4})/g,function(p,v,g){var f=g&&g.toUpperCase();return v||W[g]||r[g]||W[f].replace(/(\[[^\]]+])|(MMMM|MM|DD|dddd)/g,function(o,l,h){return l||h.slice(1)})})).match(i),z=L.length,G=0;G<z;G+=1){var E=L[G],T=R[E],d=T&&T[0],u=T&&T[1];L[G]=u?{regex:d,parser:u}:E.replace(/^\[|\]$/g,"")}return function(p){for(var v={},g=0,f=0;g<z;g+=1){var o=L[g];if(typeof o=="string")f+=o.length;else{var l=o.regex,h=o.parser,m=p.slice(f),x=l.exec(m)[0];h.call(v,x),p=p.replace(x,"")}}return function(s){var P=s.afternoon;if(P!==void 0){var e=s.hours;P?e<12&&(s.hours+=12):e===12&&(s.hours=0),delete s.afternoon}}(v),v}}return function(D,S,W){W.p.customParseFormat=!0,D&&D.parseTwoDigitYear&&(A=D.parseTwoDigitYear);var L=S.prototype,z=L.parse;L.parse=function(G){var E=G.date,T=G.utc,d=G.args;this.$u=T;var u=d[1];if(typeof u=="string"){var p=d[2]===!0,v=d[3]===!0,g=p||v,f=d[2];v&&(f=d[2]),O=this.$locale(),!p&&f&&(O=W.Ls[f]),this.$d=function(m,x,s,P){try{if(["x","X"].indexOf(x)>-1)return new Date((x==="X"?1e3:1)*m);var e=M(x)(m),w=e.year,Y=e.month,$=e.day,I=e.hours,j=e.minutes,C=e.seconds,Q=e.milliseconds,st=e.zone,ot=e.week,ft=new Date,ht=$||(w||Y?1:ft.getDate()),ct=w||ft.getFullYear(),H=0;w&&!Y||(H=Y>0?Y-1:ft.getMonth());var Z,U=I||0,rt=j||0,K=C||0,it=Q||0;return st?new Date(Date.UTC(ct,H,ht,U,rt,K,it+60*st.offset*1e3)):s?new Date(Date.UTC(ct,H,ht,U,rt,K,it)):(Z=new Date(ct,H,ht,U,rt,K,it),ot&&(Z=P(Z).week(ot).toDate()),Z)}catch{return new Date("")}}(E,u,T,W),this.init(),f&&f!==!0&&(this.$L=this.locale(f).$L),g&&E!=this.format(u)&&(this.$d=new Date("")),O={}}else if(u instanceof Array)for(var o=u.length,l=1;l<=o;l+=1){d[1]=u[l-1];var h=W.apply(this,d);if(h.isValid()){this.$d=h.$d,this.$L=h.$L,this.init();break}l===o&&(this.$d=new Date(""))}else z.call(this,G)}}})})(Jt);var We=Jt.exports;const Pe=_t(We);var te={exports:{}};(function(t,a){(function(r,i){t.exports=i()})(wt,function(){return function(r,i){var n=i.prototype,k=n.format;n.format=function(y){var _=this,O=this.$locale();if(!this.isValid())return k.bind(this)(y);var A=this.$utils(),b=(y||"YYYY-MM-DDTHH:mm:ssZ").replace(/\[([^\]]+)]|Q|wo|ww|w|WW|W|zzz|z|gggg|GGGG|Do|X|x|k{1,2}|S/g,function(F){switch(F){case"Q":return Math.ceil((_.$M+1)/3);case"Do":return O.ordinal(_.$D);case"gggg":return _.weekYear();case"GGGG":return _.isoWeekYear();case"wo":return O.ordinal(_.week(),"W");case"w":case"ww":return A.s(_.week(),F==="w"?1:2,"0");case"W":case"WW":return A.s(_.isoWeek(),F==="W"?1:2,"0");case"k":case"kk":return A.s(String(_.$H===0?24:_.$H),F==="k"?1:2,"0");case"X":return Math.floor(_.$d.getTime()/1e3);case"x":return _.$d.getTime();case"z":return"["+_.offsetName()+"]";case"zzz":return"["+_.offsetName("long")+"]";default:return F}});return k.bind(this)(b)}}})})(te);var Ve=te.exports;const Ne=_t(Ve);var ee={exports:{}};(function(t,a){(function(r,i){t.exports=i()})(wt,function(){var r,i,n=1e3,k=6e4,y=36e5,_=864e5,O=/\[([^\]]+)]|Y{1,4}|M{1,4}|D{1,2}|d{1,4}|H{1,2}|h{1,2}|a|A|m{1,2}|s{1,2}|Z{1,2}|SSS/g,A=31536e6,b=2628e6,F=/^(-|\+)?P(?:([-+]?[0-9,.]*)Y)?(?:([-+]?[0-9,.]*)M)?(?:([-+]?[0-9,.]*)W)?(?:([-+]?[0-9,.]*)D)?(?:T(?:([-+]?[0-9,.]*)H)?(?:([-+]?[0-9,.]*)M)?(?:([-+]?[0-9,.]*)S)?)?$/,V={years:A,months:b,days:_,hours:y,minutes:k,seconds:n,milliseconds:1,weeks:6048e5},N=function(E){return E instanceof z},R=function(E,T,d){return new z(E,d,T.$l)},M=function(E){return i.p(E)+"s"},D=function(E){return E<0},S=function(E){return D(E)?Math.ceil(E):Math.floor(E)},W=function(E){return Math.abs(E)},L=function(E,T){return E?D(E)?{negative:!0,format:""+W(E)+T}:{negative:!1,format:""+E+T}:{negative:!1,format:""}},z=function(){function E(d,u,p){var v=this;if(this.$d={},this.$l=p,d===void 0&&(this.$ms=0,this.parseFromMilliseconds()),u)return R(d*V[M(u)],this);if(typeof d=="number")return this.$ms=d,this.parseFromMilliseconds(),this;if(typeof d=="object")return Object.keys(d).forEach(function(o){v.$d[M(o)]=d[o]}),this.calMilliseconds(),this;if(typeof d=="string"){var g=d.match(F);if(g){var f=g.slice(2).map(function(o){return o!=null?Number(o):0});return this.$d.years=f[0],this.$d.months=f[1],this.$d.weeks=f[2],this.$d.days=f[3],this.$d.hours=f[4],this.$d.minutes=f[5],this.$d.seconds=f[6],this.calMilliseconds(),this}}return this}var T=E.prototype;return T.calMilliseconds=function(){var d=this;this.$ms=Object.keys(this.$d).reduce(function(u,p){return u+(d.$d[p]||0)*V[p]},0)},T.parseFromMilliseconds=function(){var d=this.$ms;this.$d.years=S(d/A),d%=A,this.$d.months=S(d/b),d%=b,this.$d.days=S(d/_),d%=_,this.$d.hours=S(d/y),d%=y,this.$d.minutes=S(d/k),d%=k,this.$d.seconds=S(d/n),d%=n,this.$d.milliseconds=d},T.toISOString=function(){var d=L(this.$d.years,"Y"),u=L(this.$d.months,"M"),p=+this.$d.days||0;this.$d.weeks&&(p+=7*this.$d.weeks);var v=L(p,"D"),g=L(this.$d.hours,"H"),f=L(this.$d.minutes,"M"),o=this.$d.seconds||0;this.$d.milliseconds&&(o+=this.$d.milliseconds/1e3,o=Math.round(1e3*o)/1e3);var l=L(o,"S"),h=d.negative||u.negative||v.negative||g.negative||f.negative||l.negative,m=g.format||f.format||l.format?"T":"",x=(h?"-":"")+"P"+d.format+u.format+v.format+m+g.format+f.format+l.format;return x==="P"||x==="-P"?"P0D":x},T.toJSON=function(){return this.toISOString()},T.format=function(d){var u=d||"YYYY-MM-DDTHH:mm:ss",p={Y:this.$d.years,YY:i.s(this.$d.years,2,"0"),YYYY:i.s(this.$d.years,4,"0"),M:this.$d.months,MM:i.s(this.$d.months,2,"0"),D:this.$d.days,DD:i.s(this.$d.days,2,"0"),H:this.$d.hours,HH:i.s(this.$d.hours,2,"0"),m:this.$d.minutes,mm:i.s(this.$d.minutes,2,"0"),s:this.$d.seconds,ss:i.s(this.$d.seconds,2,"0"),SSS:i.s(this.$d.milliseconds,3,"0")};return u.replace(O,function(v,g){return g||String(p[v])})},T.as=function(d){return this.$ms/V[M(d)]},T.get=function(d){var u=this.$ms,p=M(d);return p==="milliseconds"?u%=1e3:u=p==="weeks"?S(u/V[p]):this.$d[p],u||0},T.add=function(d,u,p){var v;return v=u?d*V[M(u)]:N(d)?d.$ms:R(d,this).$ms,R(this.$ms+v*(p?-1:1),this)},T.subtract=function(d,u){return this.add(d,u,!0)},T.locale=function(d){var u=this.clone();return u.$l=d,u},T.clone=function(){return R(this.$ms,this)},T.humanize=function(d){return r().add(this.$ms,"ms").locale(this.$l).fromNow(!d)},T.valueOf=function(){return this.asMilliseconds()},T.milliseconds=function(){return this.get("milliseconds")},T.asMilliseconds=function(){return this.as("milliseconds")},T.seconds=function(){return this.get("seconds")},T.asSeconds=function(){return this.as("seconds")},T.minutes=function(){return this.get("minutes")},T.asMinutes=function(){return this.as("minutes")},T.hours=function(){return this.get("hours")},T.asHours=function(){return this.as("hours")},T.days=function(){return this.get("days")},T.asDays=function(){return this.as("days")},T.weeks=function(){return this.get("weeks")},T.asWeeks=function(){return this.as("weeks")},T.months=function(){return this.get("months")},T.asMonths=function(){return this.as("months")},T.years=function(){return this.get("years")},T.asYears=function(){return this.as("years")},E}(),G=function(E,T,d){return E.add(T.years()*d,"y").add(T.months()*d,"M").add(T.days()*d,"d").add(T.hours()*d,"h").add(T.minutes()*d,"m").add(T.seconds()*d,"s").add(T.milliseconds()*d,"ms")};return function(E,T,d){r=d,i=d().$utils(),d.duration=function(v,g){var f=d.locale();return R(v,{$l:f},g)},d.isDuration=N;var u=T.prototype.add,p=T.prototype.subtract;T.prototype.add=function(v,g){return N(v)?G(this,v,1):u.bind(this)(v,g)},T.prototype.subtract=function(v,g){return N(v)?G(this,v,-1):p.bind(this)(v,g)}}})})(ee);var Re=ee.exports;const ze=_t(Re);var Ct=function(){var t=c(function(f,o,l,h){for(l=l||{},h=f.length;h--;l[f[h]]=o);return l},"o"),a=[6,8,10,12,13,14,15,16,17,18,20,21,22,23,24,25,26,27,28,29,30,31,33,35,36,38,40],r=[1,26],i=[1,27],n=[1,28],k=[1,29],y=[1,30],_=[1,31],O=[1,32],A=[1,33],b=[1,34],F=[1,9],V=[1,10],N=[1,11],R=[1,12],M=[1,13],D=[1,14],S=[1,15],W=[1,16],L=[1,19],z=[1,20],G=[1,21],E=[1,22],T=[1,23],d=[1,25],u=[1,35],p={trace:c(function(){},"trace"),yy:{},symbols_:{error:2,start:3,gantt:4,document:5,EOF:6,line:7,SPACE:8,statement:9,NL:10,weekday:11,weekday_monday:12,weekday_tuesday:13,weekday_wednesday:14,weekday_thursday:15,weekday_friday:16,weekday_saturday:17,weekday_sunday:18,weekend:19,weekend_friday:20,weekend_saturday:21,dateFormat:22,inclusiveEndDates:23,topAxis:24,axisFormat:25,tickInterval:26,excludes:27,includes:28,todayMarker:29,title:30,acc_title:31,acc_title_value:32,acc_descr:33,acc_descr_value:34,acc_descr_multiline_value:35,section:36,clickStatement:37,taskTxt:38,taskData:39,click:40,callbackname:41,callbackargs:42,href:43,clickStatementDebug:44,$accept:0,$end:1},terminals_:{2:"error",4:"gantt",6:"EOF",8:"SPACE",10:"NL",12:"weekday_monday",13:"weekday_tuesday",14:"weekday_wednesday",15:"weekday_thursday",16:"weekday_friday",17:"weekday_saturday",18:"weekday_sunday",20:"weekend_friday",21:"weekend_saturday",22:"dateFormat",23:"inclusiveEndDates",24:"topAxis",25:"axisFormat",26:"tickInterval",27:"excludes",28:"includes",29:"todayMarker",30:"title",31:"acc_title",32:"acc_title_value",33:"acc_descr",34:"acc_descr_value",35:"acc_descr_multiline_value",36:"section",38:"taskTxt",39:"taskData",40:"click",41:"callbackname",42:"callbackargs",43:"href"},productions_:[0,[3,3],[5,0],[5,2],[7,2],[7,1],[7,1],[7,1],[11,1],[11,1],[11,1],[11,1],[11,1],[11,1],[11,1],[19,1],[19,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,2],[9,2],[9,1],[9,1],[9,1],[9,2],[37,2],[37,3],[37,3],[37,4],[37,3],[37,4],[37,2],[44,2],[44,3],[44,3],[44,4],[44,3],[44,4],[44,2]],performAction:c(function(o,l,h,m,x,s,P){var e=s.length-1;switch(x){case 1:return s[e-1];case 2:this.$=[];break;case 3:s[e-1].push(s[e]),this.$=s[e-1];break;case 4:case 5:this.$=s[e];break;case 6:case 7:this.$=[];break;case 8:m.setWeekday("monday");break;case 9:m.setWeekday("tuesday");break;case 10:m.setWeekday("wednesday");break;case 11:m.setWeekday("thursday");break;case 12:m.setWeekday("friday");break;case 13:m.setWeekday("saturday");break;case 14:m.setWeekday("sunday");break;case 15:m.setWeekend("friday");break;case 16:m.setWeekend("saturday");break;case 17:m.setDateFormat(s[e].substr(11)),this.$=s[e].substr(11);break;case 18:m.enableInclusiveEndDates(),this.$=s[e].substr(18);break;case 19:m.TopAxis(),this.$=s[e].substr(8);break;case 20:m.setAxisFormat(s[e].substr(11)),this.$=s[e].substr(11);break;case 21:m.setTickInterval(s[e].substr(13)),this.$=s[e].substr(13);break;case 22:m.setExcludes(s[e].substr(9)),this.$=s[e].substr(9);break;case 23:m.setIncludes(s[e].substr(9)),this.$=s[e].substr(9);break;case 24:m.setTodayMarker(s[e].substr(12)),this.$=s[e].substr(12);break;case 27:m.setDiagramTitle(s[e].substr(6)),this.$=s[e].substr(6);break;case 28:this.$=s[e].trim(),m.setAccTitle(this.$);break;case 29:case 30:this.$=s[e].trim(),m.setAccDescription(this.$);break;case 31:m.addSection(s[e].substr(8)),this.$=s[e].substr(8);break;case 33:m.addTask(s[e-1],s[e]),this.$="task";break;case 34:this.$=s[e-1],m.setClickEvent(s[e-1],s[e],null);break;case 35:this.$=s[e-2],m.setClickEvent(s[e-2],s[e-1],s[e]);break;case 36:this.$=s[e-2],m.setClickEvent(s[e-2],s[e-1],null),m.setLink(s[e-2],s[e]);break;case 37:this.$=s[e-3],m.setClickEvent(s[e-3],s[e-2],s[e-1]),m.setLink(s[e-3],s[e]);break;case 38:this.$=s[e-2],m.setClickEvent(s[e-2],s[e],null),m.setLink(s[e-2],s[e-1]);break;case 39:this.$=s[e-3],m.setClickEvent(s[e-3],s[e-1],s[e]),m.setLink(s[e-3],s[e-2]);break;case 40:this.$=s[e-1],m.setLink(s[e-1],s[e]);break;case 41:case 47:this.$=s[e-1]+" "+s[e];break;case 42:case 43:case 45:this.$=s[e-2]+" "+s[e-1]+" "+s[e];break;case 44:case 46:this.$=s[e-3]+" "+s[e-2]+" "+s[e-1]+" "+s[e];break}},"anonymous"),table:[{3:1,4:[1,2]},{1:[3]},t(a,[2,2],{5:3}),{6:[1,4],7:5,8:[1,6],9:7,10:[1,8],11:17,12:r,13:i,14:n,15:k,16:y,17:_,18:O,19:18,20:A,21:b,22:F,23:V,24:N,25:R,26:M,27:D,28:S,29:W,30:L,31:z,33:G,35:E,36:T,37:24,38:d,40:u},t(a,[2,7],{1:[2,1]}),t(a,[2,3]),{9:36,11:17,12:r,13:i,14:n,15:k,16:y,17:_,18:O,19:18,20:A,21:b,22:F,23:V,24:N,25:R,26:M,27:D,28:S,29:W,30:L,31:z,33:G,35:E,36:T,37:24,38:d,40:u},t(a,[2,5]),t(a,[2,6]),t(a,[2,17]),t(a,[2,18]),t(a,[2,19]),t(a,[2,20]),t(a,[2,21]),t(a,[2,22]),t(a,[2,23]),t(a,[2,24]),t(a,[2,25]),t(a,[2,26]),t(a,[2,27]),{32:[1,37]},{34:[1,38]},t(a,[2,30]),t(a,[2,31]),t(a,[2,32]),{39:[1,39]},t(a,[2,8]),t(a,[2,9]),t(a,[2,10]),t(a,[2,11]),t(a,[2,12]),t(a,[2,13]),t(a,[2,14]),t(a,[2,15]),t(a,[2,16]),{41:[1,40],43:[1,41]},t(a,[2,4]),t(a,[2,28]),t(a,[2,29]),t(a,[2,33]),t(a,[2,34],{42:[1,42],43:[1,43]}),t(a,[2,40],{41:[1,44]}),t(a,[2,35],{43:[1,45]}),t(a,[2,36]),t(a,[2,38],{42:[1,46]}),t(a,[2,37]),t(a,[2,39])],defaultActions:{},parseError:c(function(o,l){if(l.recoverable)this.trace(o);else{var h=new Error(o);throw h.hash=l,h}},"parseError"),parse:c(function(o){var l=this,h=[0],m=[],x=[null],s=[],P=this.table,e="",w=0,Y=0,$=2,I=1,j=s.slice.call(arguments,1),C=Object.create(this.lexer),Q={yy:{}};for(var st in this.yy)Object.prototype.hasOwnProperty.call(this.yy,st)&&(Q.yy[st]=this.yy[st]);C.setInput(o,Q.yy),Q.yy.lexer=C,Q.yy.parser=this,typeof C.yylloc>"u"&&(C.yylloc={});var ot=C.yylloc;s.push(ot);var ft=C.options&&C.options.ranges;typeof Q.yy.parseError=="function"?this.parseError=Q.yy.parseError:this.parseError=Object.getPrototypeOf(this).parseError;function ht(q){h.length=h.length-2*q,x.length=x.length-q,s.length=s.length-q}c(ht,"popStack");function ct(){var q;return q=m.pop()||C.lex()||I,typeof q!="number"&&(q instanceof Array&&(m=q,q=m.pop()),q=l.symbols_[q]||q),q}c(ct,"lex");for(var H,Z,U,rt,K={},it,J,Rt,gt;;){if(Z=h[h.length-1],this.defaultActions[Z]?U=this.defaultActions[Z]:((H===null||typeof H>"u")&&(H=ct()),U=P[Z]&&P[Z][H]),typeof U>"u"||!U.length||!U[0]){var Dt="";gt=[];for(it in P[Z])this.terminals_[it]&&it>$&&gt.push("'"+this.terminals_[it]+"'");C.showPosition?Dt="Parse error on line "+(w+1)+`:
`+C.showPosition()+`
Expecting `+gt.join(", ")+", got '"+(this.terminals_[H]||H)+"'":Dt="Parse error on line "+(w+1)+": Unexpected "+(H==I?"end of input":"'"+(this.terminals_[H]||H)+"'"),this.parseError(Dt,{text:C.match,token:this.terminals_[H]||H,line:C.yylineno,loc:ot,expected:gt})}if(U[0]instanceof Array&&U.length>1)throw new Error("Parse Error: multiple actions possible at state: "+Z+", token: "+H);switch(U[0]){case 1:h.push(H),x.push(C.yytext),s.push(C.yylloc),h.push(U[1]),H=null,Y=C.yyleng,e=C.yytext,w=C.yylineno,ot=C.yylloc;break;case 2:if(J=this.productions_[U[1]][1],K.$=x[x.length-J],K._$={first_line:s[s.length-(J||1)].first_line,last_line:s[s.length-1].last_line,first_column:s[s.length-(J||1)].first_column,last_column:s[s.length-1].last_column},ft&&(K._$.range=[s[s.length-(J||1)].range[0],s[s.length-1].range[1]]),rt=this.performAction.apply(K,[e,Y,w,Q.yy,U[1],x,s].concat(j)),typeof rt<"u")return rt;J&&(h=h.slice(0,-1*J*2),x=x.slice(0,-1*J),s=s.slice(0,-1*J)),h.push(this.productions_[U[1]][0]),x.push(K.$),s.push(K._$),Rt=P[h[h.length-2]][h[h.length-1]],h.push(Rt);break;case 3:return!0}}return!0},"parse")},v=function(){var f={EOF:1,parseError:c(function(l,h){if(this.yy.parser)this.yy.parser.parseError(l,h);else throw new Error(l)},"parseError"),setInput:c(function(o,l){return this.yy=l||this.yy||{},this._input=o,this._more=this._backtrack=this.done=!1,this.yylineno=this.yyleng=0,this.yytext=this.matched=this.match="",this.conditionStack=["INITIAL"],this.yylloc={first_line:1,first_column:0,last_line:1,last_column:0},this.options.ranges&&(this.yylloc.range=[0,0]),this.offset=0,this},"setInput"),input:c(function(){var o=this._input[0];this.yytext+=o,this.yyleng++,this.offset++,this.match+=o,this.matched+=o;var l=o.match(/(?:\r\n?|\n).*/g);return l?(this.yylineno++,this.yylloc.last_line++):this.yylloc.last_column++,this.options.ranges&&this.yylloc.range[1]++,this._input=this._input.slice(1),o},"input"),unput:c(function(o){var l=o.length,h=o.split(/(?:\r\n?|\n)/g);this._input=o+this._input,this.yytext=this.yytext.substr(0,this.yytext.length-l),this.offset-=l;var m=this.match.split(/(?:\r\n?|\n)/g);this.match=this.match.substr(0,this.match.length-1),this.matched=this.matched.substr(0,this.matched.length-1),h.length-1&&(this.yylineno-=h.length-1);var x=this.yylloc.range;return this.yylloc={first_line:this.yylloc.first_line,last_line:this.yylineno+1,first_column:this.yylloc.first_column,last_column:h?(h.length===m.length?this.yylloc.first_column:0)+m[m.length-h.length].length-h[0].length:this.yylloc.first_column-l},this.options.ranges&&(this.yylloc.range=[x[0],x[0]+this.yyleng-l]),this.yyleng=this.yytext.length,this},"unput"),more:c(function(){return this._more=!0,this},"more"),reject:c(function(){if(this.options.backtrack_lexer)this._backtrack=!0;else return this.parseError("Lexical error on line "+(this.yylineno+1)+`. You can only invoke reject() in the lexer when the lexer is of the backtracking persuasion (options.backtrack_lexer = true).
`+this.showPosition(),{text:"",token:null,line:this.yylineno});return this},"reject"),less:c(function(o){this.unput(this.match.slice(o))},"less"),pastInput:c(function(){var o=this.matched.substr(0,this.matched.length-this.match.length);return(o.length>20?"...":"")+o.substr(-20).replace(/\n/g,"")},"pastInput"),upcomingInput:c(function(){var o=this.match;return o.length<20&&(o+=this._input.substr(0,20-o.length)),(o.substr(0,20)+(o.length>20?"...":"")).replace(/\n/g,"")},"upcomingInput"),showPosition:c(function(){var o=this.pastInput(),l=new Array(o.length+1).join("-");return o+this.upcomingInput()+`
`+l+"^"},"showPosition"),test_match:c(function(o,l){var h,m,x;if(this.options.backtrack_lexer&&(x={yylineno:this.yylineno,yylloc:{first_line:this.yylloc.first_line,last_line:this.last_line,first_column:this.yylloc.first_column,last_column:this.yylloc.last_column},yytext:this.yytext,match:this.match,matches:this.matches,matched:this.matched,yyleng:this.yyleng,offset:this.offset,_more:this._more,_input:this._input,yy:this.yy,conditionStack:this.conditionStack.slice(0),done:this.done},this.options.ranges&&(x.yylloc.range=this.yylloc.range.slice(0))),m=o[0].match(/(?:\r\n?|\n).*/g),m&&(this.yylineno+=m.length),this.yylloc={first_line:this.yylloc.last_line,last_line:this.yylineno+1,first_column:this.yylloc.last_column,last_column:m?m[m.length-1].length-m[m.length-1].match(/\r?\n?/)[0].length:this.yylloc.last_column+o[0].length},this.yytext+=o[0],this.match+=o[0],this.matches=o,this.yyleng=this.yytext.length,this.options.ranges&&(this.yylloc.range=[this.offset,this.offset+=this.yyleng]),this._more=!1,this._backtrack=!1,this._input=this._input.slice(o[0].length),this.matched+=o[0],h=this.performAction.call(this,this.yy,this,l,this.conditionStack[this.conditionStack.length-1]),this.done&&this._input&&(this.done=!1),h)return h;if(this._backtrack){for(var s in x)this[s]=x[s];return!1}return!1},"test_match"),next:c(function(){if(this.done)return this.EOF;this._input||(this.done=!0);var o,l,h,m;this._more||(this.yytext="",this.match="");for(var x=this._currentRules(),s=0;s<x.length;s++)if(h=this._input.match(this.rules[x[s]]),h&&(!l||h[0].length>l[0].length)){if(l=h,m=s,this.options.backtrack_lexer){if(o=this.test_match(h,x[s]),o!==!1)return o;if(this._backtrack){l=!1;continue}else return!1}else if(!this.options.flex)break}return l?(o=this.test_match(l,x[m]),o!==!1?o:!1):this._input===""?this.EOF:this.parseError("Lexical error on line "+(this.yylineno+1)+`. Unrecognized text.
`+this.showPosition(),{text:"",token:null,line:this.yylineno})},"next"),lex:c(function(){var l=this.next();return l||this.lex()},"lex"),begin:c(function(l){this.conditionStack.push(l)},"begin"),popState:c(function(){var l=this.conditionStack.length-1;return l>0?this.conditionStack.pop():this.conditionStack[0]},"popState"),_currentRules:c(function(){return this.conditionStack.length&&this.conditionStack[this.conditionStack.length-1]?this.conditions[this.conditionStack[this.conditionStack.length-1]].rules:this.conditions.INITIAL.rules},"_currentRules"),topState:c(function(l){return l=this.conditionStack.length-1-Math.abs(l||0),l>=0?this.conditionStack[l]:"INITIAL"},"topState"),pushState:c(function(l){this.begin(l)},"pushState"),stateStackSize:c(function(){return this.conditionStack.length},"stateStackSize"),options:{"case-insensitive":!0},performAction:c(function(l,h,m,x){switch(m){case 0:return this.begin("open_directive"),"open_directive";case 1:return this.begin("acc_title"),31;case 2:return this.popState(),"acc_title_value";case 3:return this.begin("acc_descr"),33;case 4:return this.popState(),"acc_descr_value";case 5:this.begin("acc_descr_multiline");break;case 6:this.popState();break;case 7:return"acc_descr_multiline_value";case 8:break;case 9:break;case 10:break;case 11:return 10;case 12:break;case 13:break;case 14:this.begin("href");break;case 15:this.popState();break;case 16:return 43;case 17:this.begin("callbackname");break;case 18:this.popState();break;case 19:this.popState(),this.begin("callbackargs");break;case 20:return 41;case 21:this.popState();break;case 22:return 42;case 23:this.begin("click");break;case 24:this.popState();break;case 25:return 40;case 26:return 4;case 27:return 22;case 28:return 23;case 29:return 24;case 30:return 25;case 31:return 26;case 32:return 28;case 33:return 27;case 34:return 29;case 35:return 12;case 36:return 13;case 37:return 14;case 38:return 15;case 39:return 16;case 40:return 17;case 41:return 18;case 42:return 20;case 43:return 21;case 44:return"date";case 45:return 30;case 46:return"accDescription";case 47:return 36;case 48:return 38;case 49:return 39;case 50:return":";case 51:return 6;case 52:return"INVALID"}},"anonymous"),rules:[/^(?:%%\{)/i,/^(?:accTitle\s*:\s*)/i,/^(?:(?!\n||)*[^\n]*)/i,/^(?:accDescr\s*:\s*)/i,/^(?:(?!\n||)*[^\n]*)/i,/^(?:accDescr\s*\{\s*)/i,/^(?:[\}])/i,/^(?:[^\}]*)/i,/^(?:%%(?!\{)*[^\n]*)/i,/^(?:[^\}]%%*[^\n]*)/i,/^(?:%%*[^\n]*[\n]*)/i,/^(?:[\n]+)/i,/^(?:\s+)/i,/^(?:%[^\n]*)/i,/^(?:href[\s]+["])/i,/^(?:["])/i,/^(?:[^"]*)/i,/^(?:call[\s]+)/i,/^(?:\([\s]*\))/i,/^(?:\()/i,/^(?:[^(]*)/i,/^(?:\))/i,/^(?:[^)]*)/i,/^(?:click[\s]+)/i,/^(?:[\s\n])/i,/^(?:[^\s\n]*)/i,/^(?:gantt\b)/i,/^(?:dateFormat\s[^#\n;]+)/i,/^(?:inclusiveEndDates\b)/i,/^(?:topAxis\b)/i,/^(?:axisFormat\s[^#\n;]+)/i,/^(?:tickInterval\s[^#\n;]+)/i,/^(?:includes\s[^#\n;]+)/i,/^(?:excludes\s[^#\n;]+)/i,/^(?:todayMarker\s[^\n;]+)/i,/^(?:weekday\s+monday\b)/i,/^(?:weekday\s+tuesday\b)/i,/^(?:weekday\s+wednesday\b)/i,/^(?:weekday\s+thursday\b)/i,/^(?:weekday\s+friday\b)/i,/^(?:weekday\s+saturday\b)/i,/^(?:weekday\s+sunday\b)/i,/^(?:weekend\s+friday\b)/i,/^(?:weekend\s+saturday\b)/i,/^(?:\d\d\d\d-\d\d-\d\d\b)/i,/^(?:title\s[^\n]+)/i,/^(?:accDescription\s[^#\n;]+)/i,/^(?:section\s[^\n]+)/i,/^(?:[^:\n]+)/i,/^(?::[^#\n;]+)/i,/^(?::)/i,/^(?:$)/i,/^(?:.)/i],conditions:{acc_descr_multiline:{rules:[6,7],inclusive:!1},acc_descr:{rules:[4],inclusive:!1},acc_title:{rules:[2],inclusive:!1},callbackargs:{rules:[21,22],inclusive:!1},callbackname:{rules:[18,19,20],inclusive:!1},href:{rules:[15,16],inclusive:!1},click:{rules:[24,25],inclusive:!1},INITIAL:{rules:[0,1,3,5,8,9,10,11,12,13,14,17,23,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52],inclusive:!0}}};return f}();p.lexer=v;function g(){this.yy={}}return c(g,"Parser"),g.prototype=p,p.Parser=g,new g}();Ct.parser=Ct;var He=Ct;X.extend(Oe);X.extend(Pe);X.extend(Ne);var qt={friday:5,saturday:6},tt="",$t="",Lt=void 0,Yt="",mt=[],kt=[],At=new Map,Ft=[],xt=[],dt="",Ot="",se=["active","done","crit","milestone","vert"],Wt=[],yt=!1,Pt=!1,Vt="sunday",bt="saturday",Mt=0,Be=c(function(){Ft=[],xt=[],dt="",Wt=[],pt=0,It=void 0,Tt=void 0,B=[],tt="",$t="",Ot="",Lt=void 0,Yt="",mt=[],kt=[],yt=!1,Pt=!1,Mt=0,At=new Map,Le(),Vt="sunday",bt="saturday"},"clear"),Ge=c(function(t){$t=t},"setAxisFormat"),je=c(function(){return $t},"getAxisFormat"),Xe=c(function(t){Lt=t},"setTickInterval"),Ue=c(function(){return Lt},"getTickInterval"),qe=c(function(t){Yt=t},"setTodayMarker"),Ze=c(function(){return Yt},"getTodayMarker"),Qe=c(function(t){tt=t},"setDateFormat"),Ke=c(function(){yt=!0},"enableInclusiveEndDates"),Je=c(function(){return yt},"endDatesAreInclusive"),ts=c(function(){Pt=!0},"enableTopAxis"),es=c(function(){return Pt},"topAxisEnabled"),ss=c(function(t){Ot=t},"setDisplayMode"),is=c(function(){return Ot},"getDisplayMode"),rs=c(function(){return tt},"getDateFormat"),ns=c(function(t){mt=t.toLowerCase().split(/[\s,]+/)},"setIncludes"),as=c(function(){return mt},"getIncludes"),os=c(function(t){kt=t.toLowerCase().split(/[\s,]+/)},"setExcludes"),cs=c(function(){return kt},"getExcludes"),ls=c(function(){return At},"getLinks"),us=c(function(t){dt=t,Ft.push(t)},"addSection"),ds=c(function(){return Ft},"getSections"),fs=c(function(){let t=Zt();const a=10;let r=0;for(;!t&&r<a;)t=Zt(),r++;return xt=B,xt},"getTasks"),ie=c(function(t,a,r,i){const n=t.format(a.trim()),k=t.format("YYYY-MM-DD");return i.includes(n)||i.includes(k)?!1:r.includes("weekends")&&(t.isoWeekday()===qt[bt]||t.isoWeekday()===qt[bt]+1)||r.includes(t.format("dddd").toLowerCase())?!0:r.includes(n)||r.includes(k)},"isInvalidDate"),hs=c(function(t){Vt=t},"setWeekday"),ms=c(function(){return Vt},"getWeekday"),ks=c(function(t){bt=t},"setWeekend"),re=c(function(t,a,r,i){if(!r.length||t.manualEndTime)return;let n;t.startTime instanceof Date?n=X(t.startTime):n=X(t.startTime,a,!0),n=n.add(1,"d");let k;t.endTime instanceof Date?k=X(t.endTime):k=X(t.endTime,a,!0);const[y,_]=ys(n,k,a,r,i);t.endTime=y.toDate(),t.renderEndTime=_},"checkTaskDates"),ys=c(function(t,a,r,i,n){let k=!1,y=null;for(;t<=a;)k||(y=a.toDate()),k=ie(t,r,i,n),k&&(a=a.add(1,"d")),t=t.add(1,"d");return[a,y]},"fixTaskDates"),Et=c(function(t,a,r){if(r=r.trim(),c(_=>{const O=_.trim();return O==="x"||O==="X"},"isTimestampFormat")(a)&&/^\d+$/.test(r))return new Date(Number(r));const k=/^after\s+(?<ids>[\d\w- ]+)/.exec(r);if(k!==null){let _=null;for(const A of k.groups.ids.split(" ")){let b=at(A);b!==void 0&&(!_||b.endTime>_.endTime)&&(_=b)}if(_)return _.endTime;const O=new Date;return O.setHours(0,0,0,0),O}let y=X(r,a.trim(),!0);if(y.isValid())return y.toDate();{nt.debug("Invalid date:"+r),nt.debug("With date format:"+a.trim());const _=new Date(r);if(_===void 0||isNaN(_.getTime())||_.getFullYear()<-1e4||_.getFullYear()>1e4)throw new Error("Invalid date:"+r);return _}},"getStartDate"),ne=c(function(t){const a=/^(\d+(?:\.\d+)?)([Mdhmswy]|ms)$/.exec(t.trim());return a!==null?[Number.parseFloat(a[1]),a[2]]:[NaN,"ms"]},"parseDuration"),ae=c(function(t,a,r,i=!1){r=r.trim();const k=/^until\s+(?<ids>[\d\w- ]+)/.exec(r);if(k!==null){let b=null;for(const V of k.groups.ids.split(" ")){let N=at(V);N!==void 0&&(!b||N.startTime<b.startTime)&&(b=N)}if(b)return b.startTime;const F=new Date;return F.setHours(0,0,0,0),F}let y=X(r,a.trim(),!0);if(y.isValid())return i&&(y=y.add(1,"d")),y.toDate();let _=X(t);const[O,A]=ne(r);if(!Number.isNaN(O)){const b=_.add(O,A);b.isValid()&&(_=b)}return _.toDate()},"getEndDate"),pt=0,ut=c(function(t){return t===void 0?(pt=pt+1,"task"+pt):t},"parseId"),gs=c(function(t,a){let r;a.substr(0,1)===":"?r=a.substr(1,a.length):r=a;const i=r.split(","),n={};Nt(i,n,se);for(let y=0;y<i.length;y++)i[y]=i[y].trim();let k="";switch(i.length){case 1:n.id=ut(),n.startTime=t.endTime,k=i[0];break;case 2:n.id=ut(),n.startTime=Et(void 0,tt,i[0]),k=i[1];break;case 3:n.id=ut(i[0]),n.startTime=Et(void 0,tt,i[1]),k=i[2];break}return k&&(n.endTime=ae(n.startTime,tt,k,yt),n.manualEndTime=X(k,"YYYY-MM-DD",!0).isValid(),re(n,tt,kt,mt)),n},"compileData"),vs=c(function(t,a){let r;a.substr(0,1)===":"?r=a.substr(1,a.length):r=a;const i=r.split(","),n={};Nt(i,n,se);for(let k=0;k<i.length;k++)i[k]=i[k].trim();switch(i.length){case 1:n.id=ut(),n.startTime={type:"prevTaskEnd",id:t},n.endTime={data:i[0]};break;case 2:n.id=ut(),n.startTime={type:"getStartDate",startData:i[0]},n.endTime={data:i[1]};break;case 3:n.id=ut(i[0]),n.startTime={type:"getStartDate",startData:i[1]},n.endTime={data:i[2]};break}return n},"parseData"),It,Tt,B=[],oe={},ps=c(function(t,a){const r={section:dt,type:dt,processed:!1,manualEndTime:!1,renderEndTime:null,raw:{data:a},task:t,classes:[]},i=vs(Tt,a);r.raw.startTime=i.startTime,r.raw.endTime=i.endTime,r.id=i.id,r.prevTaskId=Tt,r.active=i.active,r.done=i.done,r.crit=i.crit,r.milestone=i.milestone,r.vert=i.vert,r.order=Mt,Mt++;const n=B.push(r);Tt=r.id,oe[r.id]=n-1},"addTask"),at=c(function(t){const a=oe[t];return B[a]},"findTaskById"),Ts=c(function(t,a){const r={section:dt,type:dt,description:t,task:t,classes:[]},i=gs(It,a);r.startTime=i.startTime,r.endTime=i.endTime,r.id=i.id,r.active=i.active,r.done=i.done,r.crit=i.crit,r.milestone=i.milestone,r.vert=i.vert,It=r,xt.push(r)},"addTaskOrg"),Zt=c(function(){const t=c(function(r){const i=B[r];let n="";switch(B[r].raw.startTime.type){case"prevTaskEnd":{const k=at(i.prevTaskId);i.startTime=k.endTime;break}case"getStartDate":n=Et(void 0,tt,B[r].raw.startTime.startData),n&&(B[r].startTime=n);break}return B[r].startTime&&(B[r].endTime=ae(B[r].startTime,tt,B[r].raw.endTime.data,yt),B[r].endTime&&(B[r].processed=!0,B[r].manualEndTime=X(B[r].raw.endTime.data,"YYYY-MM-DD",!0).isValid(),re(B[r],tt,kt,mt))),B[r].processed},"compileTask");let a=!0;for(const[r,i]of B.entries())t(r),a=a&&i.processed;return a},"compileTasks"),xs=c(function(t,a){let r=a;lt().securityLevel!=="loose"&&(r=$e(a)),t.split(",").forEach(function(i){at(i)!==void 0&&(le(i,()=>{window.open(r,"_self")}),At.set(i,r))}),ce(t,"clickable")},"setLink"),ce=c(function(t,a){t.split(",").forEach(function(r){let i=at(r);i!==void 0&&i.classes.push(a)})},"setClass"),bs=c(function(t,a,r){if(lt().securityLevel!=="loose"||a===void 0)return;let i=[];if(typeof r=="string"){i=r.split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/);for(let k=0;k<i.length;k++){let y=i[k].trim();y.startsWith('"')&&y.endsWith('"')&&(y=y.substr(1,y.length-2)),i[k]=y}}i.length===0&&i.push(t),at(t)!==void 0&&le(t,()=>{Ye.runFunc(a,...i)})},"setClickFun"),le=c(function(t,a){Wt.push(function(){const r=document.querySelector(`[id="${t}"]`);r!==null&&r.addEventListener("click",function(){a()})},function(){const r=document.querySelector(`[id="${t}-text"]`);r!==null&&r.addEventListener("click",function(){a()})})},"pushFun"),ws=c(function(t,a,r){t.split(",").forEach(function(i){bs(i,a,r)}),ce(t,"clickable")},"setClickEvent"),_s=c(function(t){Wt.forEach(function(a){a(t)})},"bindFunctions"),Ds={getConfig:c(()=>lt().gantt,"getConfig"),clear:Be,setDateFormat:Qe,getDateFormat:rs,enableInclusiveEndDates:Ke,endDatesAreInclusive:Je,enableTopAxis:ts,topAxisEnabled:es,setAxisFormat:Ge,getAxisFormat:je,setTickInterval:Xe,getTickInterval:Ue,setTodayMarker:qe,getTodayMarker:Ze,setAccTitle:ke,getAccTitle:me,setDiagramTitle:he,getDiagramTitle:fe,setDisplayMode:ss,getDisplayMode:is,setAccDescription:de,getAccDescription:ue,addSection:us,getSections:ds,getTasks:fs,addTask:ps,findTaskById:at,addTaskOrg:Ts,setIncludes:ns,getIncludes:as,setExcludes:os,getExcludes:cs,setClickEvent:ws,setLink:xs,getLinks:ls,bindFunctions:_s,parseDuration:ne,isInvalidDate:ie,setWeekday:hs,getWeekday:ms,setWeekend:ks};function Nt(t,a,r){let i=!0;for(;i;)i=!1,r.forEach(function(n){const k="^\\s*"+n+"\\s*$",y=new RegExp(k);t[0].match(y)&&(a[n]=!0,t.shift(1),i=!0)})}c(Nt,"getTaskTags");X.extend(ze);var Ss=c(function(){nt.debug("Something is calling, setConf, remove the call")},"setConf"),Qt={monday:Me,tuesday:Ce,wednesday:Se,thursday:De,friday:_e,saturday:we,sunday:be},Cs=c((t,a)=>{let r=[...t].map(()=>-1/0),i=[...t].sort((k,y)=>k.startTime-y.startTime||k.order-y.order),n=0;for(const k of i)for(let y=0;y<r.length;y++)if(k.startTime>=r[y]){r[y]=k.endTime,k.order=y+a,y>n&&(n=y);break}return n},"getMaxIntersections"),et,St=1e4,Ms=c(function(t,a,r,i){const n=lt().gantt,k=lt().securityLevel;let y;k==="sandbox"&&(y=vt("#i"+a));const _=k==="sandbox"?vt(y.nodes()[0].contentDocument.body):vt("body"),O=k==="sandbox"?y.nodes()[0].contentDocument:document,A=O.getElementById(a);et=A.parentElement.offsetWidth,et===void 0&&(et=1200),n.useWidth!==void 0&&(et=n.useWidth);const b=i.db.getTasks();let F=[];for(const u of b)F.push(u.type);F=d(F);const V={};let N=2*n.topPadding;if(i.db.getDisplayMode()==="compact"||n.displayMode==="compact"){const u={};for(const v of b)u[v.section]===void 0?u[v.section]=[v]:u[v.section].push(v);let p=0;for(const v of Object.keys(u)){const g=Cs(u[v],p)+1;p+=g,N+=g*(n.barHeight+n.barGap),V[v]=g}}else{N+=b.length*(n.barHeight+n.barGap);for(const u of F)V[u]=b.filter(p=>p.type===u).length}A.setAttribute("viewBox","0 0 "+et+" "+N);const R=_.select(`[id="${a}"]`),M=ye().domain([ge(b,function(u){return u.startTime}),ve(b,function(u){return u.endTime})]).rangeRound([0,et-n.leftPadding-n.rightPadding]);function D(u,p){const v=u.startTime,g=p.startTime;let f=0;return v>g?f=1:v<g&&(f=-1),f}c(D,"taskCompare"),b.sort(D),S(b,et,N),pe(R,N,et,n.useMaxWidth),R.append("text").text(i.db.getDiagramTitle()).attr("x",et/2).attr("y",n.titleTopMargin).attr("class","titleText");function S(u,p,v){const g=n.barHeight,f=g+n.barGap,o=n.topPadding,l=n.leftPadding,h=Te().domain([0,F.length]).range(["#00B9FA","#F95002"]).interpolate(Ae);L(f,o,l,p,v,u,i.db.getExcludes(),i.db.getIncludes()),G(l,o,p,v),W(u,f,o,l,g,h,p),E(f,o),T(l,o,p,v)}c(S,"makeGantt");function W(u,p,v,g,f,o,l){u.sort((e,w)=>e.vert===w.vert?0:e.vert?1:-1);const m=[...new Set(u.map(e=>e.order))].map(e=>u.find(w=>w.order===e));R.append("g").selectAll("rect").data(m).enter().append("rect").attr("x",0).attr("y",function(e,w){return w=e.order,w*p+v-2}).attr("width",function(){return l-n.rightPadding/2}).attr("height",p).attr("class",function(e){for(const[w,Y]of F.entries())if(e.type===Y)return"section section"+w%n.numberSectionStyles;return"section section0"}).enter();const x=R.append("g").selectAll("rect").data(u).enter(),s=i.db.getLinks();if(x.append("rect").attr("id",function(e){return e.id}).attr("rx",3).attr("ry",3).attr("x",function(e){return e.milestone?M(e.startTime)+g+.5*(M(e.endTime)-M(e.startTime))-.5*f:M(e.startTime)+g}).attr("y",function(e,w){return w=e.order,e.vert?n.gridLineStartPadding:w*p+v}).attr("width",function(e){return e.milestone?f:e.vert?.08*f:M(e.renderEndTime||e.endTime)-M(e.startTime)}).attr("height",function(e){return e.vert?b.length*(n.barHeight+n.barGap)+n.barHeight*2:f}).attr("transform-origin",function(e,w){return w=e.order,(M(e.startTime)+g+.5*(M(e.endTime)-M(e.startTime))).toString()+"px "+(w*p+v+.5*f).toString()+"px"}).attr("class",function(e){const w="task";let Y="";e.classes.length>0&&(Y=e.classes.join(" "));let $=0;for(const[j,C]of F.entries())e.type===C&&($=j%n.numberSectionStyles);let I="";return e.active?e.crit?I+=" activeCrit":I=" active":e.done?e.crit?I=" doneCrit":I=" done":e.crit&&(I+=" crit"),I.length===0&&(I=" task"),e.milestone&&(I=" milestone "+I),e.vert&&(I=" vert "+I),I+=$,I+=" "+Y,w+I}),x.append("text").attr("id",function(e){return e.id+"-text"}).text(function(e){return e.task}).attr("font-size",n.fontSize).attr("x",function(e){let w=M(e.startTime),Y=M(e.renderEndTime||e.endTime);if(e.milestone&&(w+=.5*(M(e.endTime)-M(e.startTime))-.5*f,Y=w+f),e.vert)return M(e.startTime)+g;const $=this.getBBox().width;return $>Y-w?Y+$+1.5*n.leftPadding>l?w+g-5:Y+g+5:(Y-w)/2+w+g}).attr("y",function(e,w){return e.vert?n.gridLineStartPadding+b.length*(n.barHeight+n.barGap)+60:(w=e.order,w*p+n.barHeight/2+(n.fontSize/2-2)+v)}).attr("text-height",f).attr("class",function(e){const w=M(e.startTime);let Y=M(e.endTime);e.milestone&&(Y=w+f);const $=this.getBBox().width;let I="";e.classes.length>0&&(I=e.classes.join(" "));let j=0;for(const[Q,st]of F.entries())e.type===st&&(j=Q%n.numberSectionStyles);let C="";return e.active&&(e.crit?C="activeCritText"+j:C="activeText"+j),e.done?e.crit?C=C+" doneCritText"+j:C=C+" doneText"+j:e.crit&&(C=C+" critText"+j),e.milestone&&(C+=" milestoneText"),e.vert&&(C+=" vertText"),$>Y-w?Y+$+1.5*n.leftPadding>l?I+" taskTextOutsideLeft taskTextOutside"+j+" "+C:I+" taskTextOutsideRight taskTextOutside"+j+" "+C+" width-"+$:I+" taskText taskText"+j+" "+C+" width-"+$}),lt().securityLevel==="sandbox"){let e;e=vt("#i"+a);const w=e.nodes()[0].contentDocument;x.filter(function(Y){return s.has(Y.id)}).each(function(Y){var $=w.querySelector("#"+Y.id),I=w.querySelector("#"+Y.id+"-text");const j=$.parentNode;var C=w.createElement("a");C.setAttribute("xlink:href",s.get(Y.id)),C.setAttribute("target","_top"),j.appendChild(C),C.appendChild($),C.appendChild(I)})}}c(W,"drawRects");function L(u,p,v,g,f,o,l,h){if(l.length===0&&h.length===0)return;let m,x;for(const{startTime:$,endTime:I}of o)(m===void 0||$<m)&&(m=$),(x===void 0||I>x)&&(x=I);if(!m||!x)return;if(X(x).diff(X(m),"year")>5){nt.warn("The difference between the min and max time is more than 5 years. This will cause performance issues. Skipping drawing exclude days.");return}const s=i.db.getDateFormat(),P=[];let e=null,w=X(m);for(;w.valueOf()<=x;)i.db.isInvalidDate(w,s,l,h)?e?e.end=w:e={start:w,end:w}:e&&(P.push(e),e=null),w=w.add(1,"d");R.append("g").selectAll("rect").data(P).enter().append("rect").attr("id",$=>"exclude-"+$.start.format("YYYY-MM-DD")).attr("x",$=>M($.start.startOf("day"))+v).attr("y",n.gridLineStartPadding).attr("width",$=>M($.end.endOf("day"))-M($.start.startOf("day"))).attr("height",f-p-n.gridLineStartPadding).attr("transform-origin",function($,I){return(M($.start)+v+.5*(M($.end)-M($.start))).toString()+"px "+(I*u+.5*f).toString()+"px"}).attr("class","exclude-range")}c(L,"drawExcludeDays");function z(u,p,v,g){if(v<=0||u>p)return 1/0;const f=p-u,o=X.duration({[g??"day"]:v}).asMilliseconds();return o<=0?1/0:Math.ceil(f/o)}c(z,"getEstimatedTickCount");function G(u,p,v,g){const f=i.db.getDateFormat(),o=i.db.getAxisFormat();let l;o?l=o:f==="D"?l="%d":l=n.axisFormat??"%Y-%m-%d";let h=xe(M).tickSize(-g+p+n.gridLineStartPadding).tickFormat(zt(l));const x=/^([1-9]\d*)(millisecond|second|minute|hour|day|week|month)$/.exec(i.db.getTickInterval()||n.tickInterval);if(x!==null){const s=parseInt(x[1],10);if(isNaN(s)||s<=0)nt.warn(`Invalid tick interval value: "${x[1]}". Skipping custom tick interval.`);else{const P=x[2],e=i.db.getWeekday()||n.weekday,w=M.domain(),Y=w[0],$=w[1],I=z(Y,$,s,P);if(I>St)nt.warn(`The tick interval "${s}${P}" would generate ${I} ticks, which exceeds the maximum allowed (${St}). This may indicate an invalid date or time range. Skipping custom tick interval.`);else switch(P){case"millisecond":h.ticks(Ut.every(s));break;case"second":h.ticks(Xt.every(s));break;case"minute":h.ticks(jt.every(s));break;case"hour":h.ticks(Gt.every(s));break;case"day":h.ticks(Bt.every(s));break;case"week":h.ticks(Qt[e].every(s));break;case"month":h.ticks(Ht.every(s));break}}}if(R.append("g").attr("class","grid").attr("transform","translate("+u+", "+(g-50)+")").call(h).selectAll("text").style("text-anchor","middle").attr("fill","#000").attr("stroke","none").attr("font-size",10).attr("dy","1em"),i.db.topAxisEnabled()||n.topAxis){let s=Ee(M).tickSize(-g+p+n.gridLineStartPadding).tickFormat(zt(l));if(x!==null){const P=parseInt(x[1],10);if(isNaN(P)||P<=0)nt.warn(`Invalid tick interval value: "${x[1]}". Skipping custom tick interval.`);else{const e=x[2],w=i.db.getWeekday()||n.weekday,Y=M.domain(),$=Y[0],I=Y[1];if(z($,I,P,e)<=St)switch(e){case"millisecond":s.ticks(Ut.every(P));break;case"second":s.ticks(Xt.every(P));break;case"minute":s.ticks(jt.every(P));break;case"hour":s.ticks(Gt.every(P));break;case"day":s.ticks(Bt.every(P));break;case"week":s.ticks(Qt[w].every(P));break;case"month":s.ticks(Ht.every(P));break}}}R.append("g").attr("class","grid").attr("transform","translate("+u+", "+p+")").call(s).selectAll("text").style("text-anchor","middle").attr("fill","#000").attr("stroke","none").attr("font-size",10)}}c(G,"makeGrid");function E(u,p){let v=0;const g=Object.keys(V).map(f=>[f,V[f]]);R.append("g").selectAll("text").data(g).enter().append(function(f){const o=f[0].split(Ie.lineBreakRegex),l=-(o.length-1)/2,h=O.createElementNS("http://www.w3.org/2000/svg","text");h.setAttribute("dy",l+"em");for(const[m,x]of o.entries()){const s=O.createElementNS("http://www.w3.org/2000/svg","tspan");s.setAttribute("alignment-baseline","central"),s.setAttribute("x","10"),m>0&&s.setAttribute("dy","1em"),s.textContent=x,h.appendChild(s)}return h}).attr("x",10).attr("y",function(f,o){if(o>0)for(let l=0;l<o;l++)return v+=g[o-1][1],f[1]*u/2+v*u+p;else return f[1]*u/2+p}).attr("font-size",n.sectionFontSize).attr("class",function(f){for(const[o,l]of F.entries())if(f[0]===l)return"sectionTitle sectionTitle"+o%n.numberSectionStyles;return"sectionTitle"})}c(E,"vertLabels");function T(u,p,v,g){const f=i.db.getTodayMarker();if(f==="off")return;const o=R.append("g").attr("class","today"),l=new Date,h=o.append("line");h.attr("x1",M(l)+u).attr("x2",M(l)+u).attr("y1",n.titleTopMargin).attr("y2",g-n.titleTopMargin).attr("class","today"),f!==""&&h.attr("style",f.replace(/,/g,";"))}c(T,"drawToday");function d(u){const p={},v=[];for(let g=0,f=u.length;g<f;++g)Object.prototype.hasOwnProperty.call(p,u[g])||(p[u[g]]=!0,v.push(u[g]));return v}c(d,"checkUnique")},"draw"),Es={setConf:Ss,draw:Ms},Is=c(t=>`
  .mermaid-main-font {
        font-family: ${t.fontFamily};
  }

  .exclude-range {
    fill: ${t.excludeBkgColor};
  }

  .section {
    stroke: none;
    opacity: 0.2;
  }

  .section0 {
    fill: ${t.sectionBkgColor};
  }

  .section2 {
    fill: ${t.sectionBkgColor2};
  }

  .section1,
  .section3 {
    fill: ${t.altSectionBkgColor};
    opacity: 0.2;
  }

  .sectionTitle0 {
    fill: ${t.titleColor};
  }

  .sectionTitle1 {
    fill: ${t.titleColor};
  }

  .sectionTitle2 {
    fill: ${t.titleColor};
  }

  .sectionTitle3 {
    fill: ${t.titleColor};
  }

  .sectionTitle {
    text-anchor: start;
    font-family: ${t.fontFamily};
  }


  /* Grid and axis */

  .grid .tick {
    stroke: ${t.gridColor};
    opacity: 0.8;
    shape-rendering: crispEdges;
  }

  .grid .tick text {
    font-family: ${t.fontFamily};
    fill: ${t.textColor};
  }

  .grid path {
    stroke-width: 0;
  }


  /* Today line */

  .today {
    fill: none;
    stroke: ${t.todayLineColor};
    stroke-width: 2px;
  }


  /* Task styling */

  /* Default task */

  .task {
    stroke-width: 2;
  }

  .taskText {
    text-anchor: middle;
    font-family: ${t.fontFamily};
  }

  .taskTextOutsideRight {
    fill: ${t.taskTextDarkColor};
    text-anchor: start;
    font-family: ${t.fontFamily};
  }

  .taskTextOutsideLeft {
    fill: ${t.taskTextDarkColor};
    text-anchor: end;
  }


  /* Special case clickable */

  .task.clickable {
    cursor: pointer;
  }

  .taskText.clickable {
    cursor: pointer;
    fill: ${t.taskTextClickableColor} !important;
    font-weight: bold;
  }

  .taskTextOutsideLeft.clickable {
    cursor: pointer;
    fill: ${t.taskTextClickableColor} !important;
    font-weight: bold;
  }

  .taskTextOutsideRight.clickable {
    cursor: pointer;
    fill: ${t.taskTextClickableColor} !important;
    font-weight: bold;
  }


  /* Specific task settings for the sections*/

  .taskText0,
  .taskText1,
  .taskText2,
  .taskText3 {
    fill: ${t.taskTextColor};
  }

  .task0,
  .task1,
  .task2,
  .task3 {
    fill: ${t.taskBkgColor};
    stroke: ${t.taskBorderColor};
  }

  .taskTextOutside0,
  .taskTextOutside2
  {
    fill: ${t.taskTextOutsideColor};
  }

  .taskTextOutside1,
  .taskTextOutside3 {
    fill: ${t.taskTextOutsideColor};
  }


  /* Active task */

  .active0,
  .active1,
  .active2,
  .active3 {
    fill: ${t.activeTaskBkgColor};
    stroke: ${t.activeTaskBorderColor};
  }

  .activeText0,
  .activeText1,
  .activeText2,
  .activeText3 {
    fill: ${t.taskTextDarkColor} !important;
  }


  /* Completed task */

  .done0,
  .done1,
  .done2,
  .done3 {
    stroke: ${t.doneTaskBorderColor};
    fill: ${t.doneTaskBkgColor};
    stroke-width: 2;
  }

  .doneText0,
  .doneText1,
  .doneText2,
  .doneText3 {
    fill: ${t.taskTextDarkColor} !important;
  }

  /* Done task text displayed outside the bar sits against the diagram background,
     not against the done-task bar, so it must use the outside/contrast color. */
  .doneText0.taskTextOutsideLeft,
  .doneText0.taskTextOutsideRight,
  .doneText1.taskTextOutsideLeft,
  .doneText1.taskTextOutsideRight,
  .doneText2.taskTextOutsideLeft,
  .doneText2.taskTextOutsideRight,
  .doneText3.taskTextOutsideLeft,
  .doneText3.taskTextOutsideRight {
    fill: ${t.taskTextOutsideColor} !important;
  }


  /* Tasks on the critical line */

  .crit0,
  .crit1,
  .crit2,
  .crit3 {
    stroke: ${t.critBorderColor};
    fill: ${t.critBkgColor};
    stroke-width: 2;
  }

  .activeCrit0,
  .activeCrit1,
  .activeCrit2,
  .activeCrit3 {
    stroke: ${t.critBorderColor};
    fill: ${t.activeTaskBkgColor};
    stroke-width: 2;
  }

  .doneCrit0,
  .doneCrit1,
  .doneCrit2,
  .doneCrit3 {
    stroke: ${t.critBorderColor};
    fill: ${t.doneTaskBkgColor};
    stroke-width: 2;
    cursor: pointer;
    shape-rendering: crispEdges;
  }

  .milestone {
    transform: rotate(45deg) scale(0.8,0.8);
  }

  .milestoneText {
    font-style: italic;
  }
  .doneCritText0,
  .doneCritText1,
  .doneCritText2,
  .doneCritText3 {
    fill: ${t.taskTextDarkColor} !important;
  }

  /* Done-crit task text outside the bar — same reasoning as doneText above. */
  .doneCritText0.taskTextOutsideLeft,
  .doneCritText0.taskTextOutsideRight,
  .doneCritText1.taskTextOutsideLeft,
  .doneCritText1.taskTextOutsideRight,
  .doneCritText2.taskTextOutsideLeft,
  .doneCritText2.taskTextOutsideRight,
  .doneCritText3.taskTextOutsideLeft,
  .doneCritText3.taskTextOutsideRight {
    fill: ${t.taskTextOutsideColor} !important;
  }

  .vert {
    stroke: ${t.vertLineColor};
  }

  .vertText {
    font-size: 15px;
    text-anchor: middle;
    fill: ${t.vertLineColor} !important;
  }

  .activeCritText0,
  .activeCritText1,
  .activeCritText2,
  .activeCritText3 {
    fill: ${t.taskTextDarkColor} !important;
  }

  .titleText {
    text-anchor: middle;
    font-size: 18px;
    fill: ${t.titleColor||t.textColor};
    font-family: ${t.fontFamily};
  }
`,"getStyles"),$s=Is,Os={parser:He,db:Ds,renderer:Es,styles:$s};export{Os as diagram};
