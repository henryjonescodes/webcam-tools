import streamDeck from "@elgato/streamdeck";

import { DialControlAction } from "./actions/dial";
import { LaunchAction } from "./actions/launch";
import { LiveFeedAction } from "./actions/livefeed";
import { OpenFolderAction } from "./actions/openfolder";
import { OpenWebAction } from "./actions/openweb";
import { PipelineToggleAction } from "./actions/pipelinetoggle";
import { RecordClipButtonAction } from "./actions/recordclip";
import { RecordingStatusAction } from "./actions/recordingstatus";
import { ResetAction } from "./actions/reset";
import { RotateAction } from "./actions/rotate";
import { StatusAction } from "./actions/status";
import { VideoCellAction } from "./actions/videocell";

streamDeck.logger.setLevel("info");

streamDeck.actions.registerAction(new LaunchAction());
streamDeck.actions.registerAction(new StatusAction());
streamDeck.actions.registerAction(new RecordingStatusAction());
streamDeck.actions.registerAction(new OpenWebAction());
streamDeck.actions.registerAction(new OpenFolderAction());
streamDeck.actions.registerAction(new LiveFeedAction());
streamDeck.actions.registerAction(new DialControlAction());
streamDeck.actions.registerAction(new VideoCellAction());
streamDeck.actions.registerAction(new ResetAction());
streamDeck.actions.registerAction(new RotateAction());
streamDeck.actions.registerAction(new RecordClipButtonAction());
streamDeck.actions.registerAction(new PipelineToggleAction());

streamDeck.connect();
