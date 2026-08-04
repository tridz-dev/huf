import { lazy, Suspense, useEffect } from 'react';
import {
	createBrowserRouter,
	RouterProvider,
	Navigate,
	useLocation,
	Outlet,
} from 'react-router-dom';
import { UserProvider } from './contexts/UserContext';
import { PermissionsProvider, usePermissions } from './contexts/PermissionsContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AppShellLayout } from './layouts/AppShellLayout';
import { PageLoader } from './components/PageLoader';
import { Toaster } from './components/ui/sonner';
import { RouteErrorBoundary, clearChunkReloadFlag } from './components/RouteErrorBoundary';
import { initTheme } from './lib/personalization';
import { SocketProvider } from './contexts/SocketContext';
import {
	checkStreamingAvailable,
	setStreamingAvailable,
} from './services/streamChatApi';

const ChatOnlyPage = lazy(() => import('./pages/ChatOnlyPage'));
const PreviewViewPage = lazy(() => import('./pages/PreviewViewPage'));
const ArtifactViewPage = lazy(() => import('./pages/ArtifactViewPage'));

function ChatOnlyRedirectGuard() {
	const location = useLocation();
	const { capabilities, isLoading } = usePermissions();
	const isChatOnlyUser =
		capabilities.includes('chat.use') &&
		capabilities.every((capability) => capability.startsWith('chat.'));
	const isAllowedChatOnlyPath =
		location.pathname.startsWith('/ui/chat') || location.pathname.startsWith('/view/');

	if (isLoading || !isChatOnlyUser || isAllowedChatOnlyPath) {
		return null;
	}

	return <Navigate to="/ui/chat" replace />;
}

function RootLayout() {
	useEffect(() => {
		clearChunkReloadFlag();
	}, []);

	useEffect(() => {
		initTheme();
	}, []);

	return (
		<SocketProvider>
			<UserProvider>
				<PermissionsProvider>
					<ChatOnlyRedirectGuard />
					<Outlet />
					<Toaster />
				</PermissionsProvider>
			</UserProvider>
		</SocketProvider>
	);
}

function LazyChatOnlyPage() {
	return (
		<Suspense fallback={<PageLoader />}>
			<ChatOnlyPage />
		</Suspense>
	);
}

function LazyPreviewViewPage() {
	return (
		<Suspense fallback={<PageLoader />}>
			<PreviewViewPage />
		</Suspense>
	);
}

function LazyArtifactViewPage() {
	return (
		<Suspense fallback={<PageLoader />}>
			<ArtifactViewPage />
		</Suspense>
	);
}

const router = createBrowserRouter(
	[
		{
			path: '/',
			element: <RootLayout />,
			errorElement: <RouteErrorBoundary />,
			children: [
				{
					path: 'ui/chat',
					element: (
						<ProtectedRoute>
							<LazyChatOnlyPage />
						</ProtectedRoute>
					),
				},
				{
					path: 'ui/chat/:chatId',
					element: (
						<ProtectedRoute>
							<LazyChatOnlyPage />
						</ProtectedRoute>
					),
				},
				{
					path: 'view/:messageId',
					element: (
						<ProtectedRoute>
							<LazyPreviewViewPage />
						</ProtectedRoute>
					),
				},
				{
					// Standalone like /view/:messageId — the page is h-screen and
					// renders no shell chrome of its own.
					path: 'artifact/:artifactId',
					element: (
						<ProtectedRoute>
							<LazyArtifactViewPage />
						</ProtectedRoute>
					),
				},
				{
					element: <ProtectedRoute />,
					children: [
						{
							index: true,
							element: <AppShellLayout />,
						},
						{
							path: '*',
							element: <AppShellLayout />,
						},
					],
				},
			],
		},
	],
	{ basename: '/huf' },
);

function App() {
	useEffect(() => {
		checkStreamingAvailable().then((ok) => {
			console.log('Streaming available:', ok);
			setStreamingAvailable(ok);
		});
	}, []);

	return <RouterProvider router={router} />;
}

export default App;
